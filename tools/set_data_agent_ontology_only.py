"""Remove the standalone model from the owned Data Agent, preserving other state."""

import argparse
from base64 import b64decode, b64encode
from hashlib import sha256
import json
import sys

from bootstrap_dev_context import data_agent_documents
from bootstrap_fabric_items import MARKER, post_and_wait
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    workspace = stage["workspace_id"]
    configured = stage["items"]["DA_Sales"]
    local = ROOT / "fabric" / "DA_Sales.DataAgent"
    for name, expected in configured.get("local_files", {}).items():
        target = local / name
        if not target.is_file() or sha256(target.read_bytes()).hexdigest() != expected:
            raise ContextError(f"Local agent source changed outside automation: {name}; not overwritten.")
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    detail = api.request("GET", f"/v1/workspaces/{workspace}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if detail["displayName"] != stage["workspace_name"] or \
            detail["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("The target differs from the approved Dev workspace/Active F4.")
    matches = [item for item in api.list(f"/v1/workspaces/{workspace}/items?type=DataAgent")
               if item["displayName"] == "DA_Sales"]
    if len(matches) != 1 or matches[0]["id"] != configured["id"] or \
            not (matches[0].get("description") or "").startswith(MARKER):
        raise ContextError("Refusing to change an unowned or conflicting Data Agent.")
    endpoint = f"/v1/workspaces/{workspace}/dataAgents/{configured['id']}"
    current = post_and_wait(api, endpoint + "/getDefinition", {}, False, "Read DA_Sales")
    parts = current["definition"]["parts"]
    model_id = stage["items"]["SM_Sales"]["id"]
    remove_prefixes = []
    for part in parts:
        if part["path"].startswith("Files/Config/draft/") and part["path"].endswith("/datasource.json"):
            source = json.loads(b64decode(part["payload"]))
            if source.get("type") == "semantic_model" and source.get("artifactId") == model_id:
                remove_prefixes.append(part["path"].rsplit("/", 1)[0] + "/")
    replacement = []
    changed = False
    stage_path = "Files/Config/draft/stage_config.json"
    for part in parts:
        if any(part["path"].startswith(prefix) for prefix in remove_prefixes):
            changed = True
            continue
        if part["path"] == stage_path:
            body = json.loads(b64decode(part["payload"]))
            text = body.get("aiInstructions", "")
            if not isinstance(text, str):
                raise ApiError("The current draft instructions are not text; no replacement made.")
            old_routing = ("Use SM_Sales measures for actuals, forecast, deviation, revenue and margin.\n"
                           "Use ONT_Business for business terms (package/Gebinde, channel, region, partner).")
            new_routing = ("Use ONT_Business as the only configured agent context source.\n"
                           "Resolve business terms, metrics and query bindings through the ontology.\n"
                           "Query its eligible underlying data sources; do not add SM_Sales independently.")
            updated = text.replace(old_routing, new_routing)
            if new_routing not in updated:
                updated = updated.rstrip() + "\n\n" + new_routing + "\n"
            if updated != text:
                body["aiInstructions"] = updated
                part = {**part, "payload": b64encode((json.dumps(body, indent=2) + "\n").encode()).decode()}
                changed = True
        replacement.append(part)
    if not any(part["path"] == stage_path for part in replacement):
        raise ApiError("The current agent has no draft instruction file; no replacement made.")
    if changed:
        post_and_wait(api, endpoint + "/updateDefinition", {"definition": {"parts": replacement}},
                      args.dry_run, "Ontology-only DA_Sales", retrieve_result=False)
    if args.dry_run:
        print("DRY-RUN: remove only the standalone draft model source and update agent routing; report unchanged.")
        return
    result = post_and_wait(api, endpoint + "/getDefinition", {}, False, "Verify DA_Sales")
    verified_instructions = None
    for part in result["definition"]["parts"]:
        if part["path"] == stage_path:
            verified_instructions = json.loads(b64decode(part["payload"]))
        if part["path"].startswith("Files/Config/draft/") and part["path"].endswith("/datasource.json"):
            source = json.loads(b64decode(part["payload"]))
            if source.get("type") == "semantic_model" and source.get("artifactId") == model_id:
                raise ApiError("A standalone SM_Sales agent source is still present.")
    if not verified_instructions or new_routing not in verified_instructions.get("aiInstructions", ""):
        raise ApiError("Ontology-only agent routing did not persist.")
    documents = data_agent_documents()
    documents[stage_path] = verified_instructions
    for name in configured.get("local_files", {}):
        if name.endswith("/datasource.json") and name not in documents:
            target = local / name
            if json.loads(target.read_text(encoding="utf-8")).get("artifactId") == model_id:
                target.unlink()
    for name, body in documents.items():
        target = local / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    configured["local_files"] = {name: sha256((local / name).read_bytes()).hexdigest()
                                  for name in [*documents, ".platform"]}
    wanted = [{"path": path, "payload": b64encode((json.dumps(body, indent=2) + "\n").encode()).decode(),
               "payloadType": "InlineBase64"} for path, body in documents.items()]
    configured["definition_sha256"] = sha256(json.dumps(wanted, sort_keys=True).encode()).hexdigest()
    configured["source_policy"] = "ontology-only"
    configured.setdefault("ontology_context_pending", True)
    save_config(config)
    record("DA_Sales standalone SM_Sales source removed and verified. Ontology-only agent routing "
           "persisted; other definition parts and published state preserved. RPT_Sales/SM_Sales "
           "were not changed. Reference: common/COMMON-CORE.md; "
           "https://learn.microsoft.com/rest/api/fabric/dataagent/items/update-data-agent-definition.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError, OSError, ValueError) as error:
        record(f"Ontology-only Data Agent update blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
