"""Capture the manual ontology, create a draft data agent and stage Variable Library."""

import argparse
from base64 import b64encode, b64decode
from hashlib import sha256
import json
import sys
from uuid import NAMESPACE_URL, uuid5

from bootstrap_fabric_items import MARKER, create_item, post_and_wait
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

INSTRUCTIONS = """You answer sales and forecast questions for a beverage company.
Volumes are in hectolitres (hl), money in EUR. Months are first-of-month dates.
Use ONT_Business as the only configured agent context source.
Resolve business terms, metrics and query bindings through the ontology.
Query its eligible underlying data sources; do not add SM_Sales independently.
Always state the period and filters you used. Never estimate missing values.
Partner delivery records have a different grain from sales; never multiply sales
metrics by joining multi-partner deliveries.

Example questions:
1. What was actual volume by region in October 2026?
2. Which package type had the largest forecast deviation in October 2026 in North?
3. Compare actual and forecast volume by channel for Q3 2026.
4. Compare actual versus forecast for PET 1.0 l in August-October 2026.
5. What was the revenue-weighted margin percentage by channel in October 2026?
"""
AGENT_REFERENCES = (
    "fabric-skills/common/COMMON-CORE.md; "
    "https://learn.microsoft.com/rest/api/fabric/dataagent/items/create-data-agent; "
    "https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/data-agent-definition")


def data_agent_documents() -> dict:
    return {
        "Files/Config/data_agent.json": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataAgent/2.1.0/schema.json"},
        "Files/Config/draft/stage_config.json": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/stageConfiguration/1.0.0/schema.json",
            "aiInstructions": INSTRUCTIONS}}


def ensure_item(api: Api, stage: dict, name: str, kind: str, documents: dict,
                config: dict, dry_run: bool, endpoint: str) -> dict | None:
    workspace = stage["workspace_id"]
    parts = [{"path": path, "payload": b64encode((json.dumps(body, indent=2) + "\n").encode()).decode(),
              "payloadType": "InlineBase64"} for path, body in documents.items()]
    digest = sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    configured = stage["items"].get(name, {})
    folder = ROOT / "fabric" / f"{name}.{kind}"
    if folder.exists():
        marker = folder / ".platform"
        if not marker.is_file() or not json.loads(marker.read_text(encoding="utf-8"))["metadata"]["description"].startswith(MARKER):
            raise ContextError(f"Existing local {name} folder is unowned.")
        for path, expected in configured.get("local_files", {}).items():
            target = folder / path
            if not target.is_file() or sha256(target.read_bytes()).hexdigest() != expected:
                raise ContextError(f"Local {name} source changed outside automation: {path}.")
    matches = [item for item in api.list(f"/v1/workspaces/{workspace}/items?type={kind}")
               if item["displayName"] == name]
    if matches:
        if len(matches) != 1 or not (matches[0].get("description") or "").startswith(MARKER) or \
                configured.get("id") != matches[0]["id"] or configured.get("definition_sha256") != digest:
            raise ContextError(f"Existing {name} differs or is unowned; no definition overwrite.")
        item = matches[0]
    else:
        item = create_item(api, endpoint, {"displayName": name, "description": MARKER + f": {name}.",
                           **({"type": kind} if endpoint.endswith("/items") else {}),
                           "definition": {"parts": parts}}, dry_run)
        if dry_run:
            return None
        configured = stage["items"].setdefault(name, {})
        configured.update({"id": item["id"], "type": kind, "definition_sha256": digest})
        save_config(config)
    if not dry_run:
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": name, "description": MARKER + f": {name}."},
            "config": {"version": "2.0", "logicalId": str(uuid5(NAMESPACE_URL, f"fabric-demo-platform/{name}"))}}
        for path, body in {**documents, ".platform": platform}.items():
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        configured["local_files"] = {
            path: sha256((folder / path).read_bytes()).hexdigest()
            for path in [*documents, ".platform"]}
        save_config(config)
        record(f"Created/verified {name} `{item['id']}` with owned definition; no unowned overwrite.")
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    workspace = stage["workspace_id"]
    core = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
               skill="e2e-medallion-architecture")
    detail = core.request("GET", f"/v1/workspaces/{workspace}")
    capacities = [item for item in core.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if detail["displayName"] != stage["workspace_name"] or \
            detail["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Dev context is not the existing approved Active F4.")
    ontologies = [item for item in core.list(f"/v1/workspaces/{workspace}/items?type=Ontology")
                  if item["displayName"] == "ONT_Business"]
    if len(ontologies) != 1:
        raise ContextError("The user-confirmed ONT_Business could not be resolved uniquely.")
    ontology = ontologies[0]
    prior = stage["items"].get("ONT_Business", {})
    if prior.get("id") not in (None, ontology["id"]):
        raise ContextError("The recorded ontology identity changed; no rebind.")
    if not args.dry_run:
        stage["items"]["ONT_Business"] = {**prior, "id": ontology["id"], "type": "Ontology",
                                          "user_created": True, "v2_configuration_user_confirmed": True}
        save_config(config)
        record(f"Captured user-created V2 ONT_Business `{ontology['id']}` metadata; "
               "entity/binding configuration confirmed by user, not inspected through a V1 API.")
    model = stage["items"]["SM_Sales"]
    agent_documents = data_agent_documents()
    agent = ensure_item(core, stage, "DA_Sales", "DataAgent", agent_documents, config,
                        args.dry_run, f"/v1/workspaces/{workspace}/dataAgents")
    if agent and not args.dry_run:
        definition = post_and_wait(core, f"/v1/workspaces/{workspace}/dataAgents/{agent['id']}/getDefinition",
                                   {}, False, "DA_Sales definition")
        returned = {part["path"]: json.loads(b64decode(part["payload"]))
                    for part in definition["definition"]["parts"]
                    if part["path"].endswith(("stage_config.json", "datasource.json"))}
        model_sources = [body for path, body in returned.items()
                         if path.startswith("Files/Config/draft/") and path.endswith("datasource.json")
                         and body.get("type") == "semantic_model" and body.get("artifactId") == model["id"]]
        if returned.get("Files/Config/draft/stage_config.json", {}).get("aiInstructions") != INSTRUCTIONS or \
                model_sources:
            raise ApiError("Data Agent ontology-only instructions or source policy did not persist.")
        stage["items"]["DA_Sales"].setdefault("ontology_context_pending", True)
        save_config(config)
        record(f"DA_Sales ontology-only draft instructions and absence of a standalone SM_Sales source readback PASS. "
               f"V2 Ontology context must be attached in the supported UI, not as graph/GQL. References: {AGENT_REFERENCES}.")
    vl = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="variable-library-cli")
    defaults = {"catalog": stage["databricks_catalog"], "sp_folder": stage["sharepoint_folder"], "env_label": "dev"}
    documents = {
        "variables.json": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/variables/1.0.0/schema.json",
            "variables": [{"name": name, "type": "String", "value": value} for name, value in defaults.items()]},
        "settings.json": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/settings/1.0.0/schema.json",
            "valueSetsOrder": ["dev", "test", "prod"]}}
    for name in ("dev", "test", "prod"):
        values = {"catalog": config["environments"][name]["databricks_catalog"],
                  "sp_folder": config["environments"][name]["sharepoint_folder"], "env_label": name}
        documents[f"valueSets/{name}.json"] = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/valueSet/1.0.0/schema.json",
            "name": name, "variableOverrides": [{"name": key, "value": value}
                                               for key, value in values.items() if value != defaults[key]]}
    library = ensure_item(vl, stage, "VL_Config", "VariableLibrary", documents, config,
                          args.dry_run, f"/v1/workspaces/{workspace}/items")
    if library and not args.dry_run:
        path = f"/v1/workspaces/{workspace}/variableLibraries/{library['id']}"
        state = vl.request("GET", path)
        if state["properties"]["activeValueSetName"] != "dev":
            vl.request("PATCH", path, {"properties": {"activeValueSetName": "dev"}})
            state = vl.request("GET", path)
        if state["properties"]["activeValueSetName"] != "dev":
            raise ApiError("VL_Config active dev value set did not persist.")
        definition = post_and_wait(vl, f"/v1/workspaces/{workspace}/items/{library['id']}/getDefinition",
                                   {}, False, "VL_Config definition")
        returned = {part["path"]: json.loads(b64decode(part["payload"]))
                    for part in definition["definition"]["parts"] if part["path"] in documents}
        if returned != documents:
            raise ApiError("Variable Library values or value sets differ from the requested definition.")
        stage["items"]["VL_Config"]["active_value_set"] = "dev"
        save_config(config)
        record("VL_Config definition/readback and active dev value set PASS; "
               "no redundant dev overrides. Skill: variable-library-cli/references/authoring.md; operations.md.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError, ValueError, OSError) as error:
        record(f"Dev context bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
