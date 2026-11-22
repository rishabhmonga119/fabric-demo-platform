"""Deploy the MCP-authored Sales model once, bind end-user SSO, and optionally refresh."""

import argparse
from base64 import b64encode
from decimal import Decimal
from hashlib import sha256
import json
import sys
import time
from uuid import NAMESPACE_URL, uuid5

from bootstrap_fabric_items import MARKER, create_item
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = ("powerbi-authoring/skills/semantic-model-authoring/references/"
              "semantic-model-rest-api.md; connection-binding.md; direct-lake-guidelines.md; "
              "https://learn.microsoft.com/rest/api/power-bi/datasets/execute-queries-in-group")


def definition_parts(folder):
    files = [folder / "definition.pbism", *sorted((folder / "definition").rglob("*.tmdl"))]
    required = [folder / "definition" / name for name in ("database.tmdl", "model.tmdl")]
    if len(files) < 4 or not all(path.is_file() for path in [*required, files[0]]):
        raise ContextError("Export the complete SM_Sales model from modeling MCP before deployment.")
    parts = [{"path": path.relative_to(folder).as_posix(),
              "payload": b64encode(path.read_bytes()).decode(), "payloadType": "InlineBase64"}
             for path in files]
    return parts, sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def refresh_and_check(pbi, root, configured, config):
    history = pbi.list(root + "/refreshes?$top=10")
    recorded = configured.get("last_refresh_id")
    if recorded:
        prior = [item for item in history if item.get("requestId") == recorded]
    else:
        prior = [item for item in history if item.get("refreshType") == "ViaEnhancedApi"]
    if prior:
        latest = prior[0]
        configured["last_refresh_id"] = latest["requestId"]
        configured["last_refresh_state"] = latest["status"]
        save_config(config)
        if latest["status"] not in ("Completed", "Unknown", "InProgress"):
            raise ApiError(f"Recorded model refresh {latest['status']}; no automatic resubmission.")
        record(f"Reconciled existing SM_Sales refresh `{latest['requestId']}`: {latest['status']}; "
               "no new refresh submission.")
    active = [item for item in history if item["status"] in ("Unknown", "InProgress")]
    if len(active) > 1:
        raise ContextError("Multiple model refreshes are active; no duplicate submission.")
    if active:
        refresh_id = active[0]["requestId"]
    elif configured.get("last_refresh_state") == "Completed":
        refresh_id = None
    else:
        response = pbi.request("POST", root + "/refreshes",
                               {"type": "full", "commitMode": "transactional",
                                "retryCount": 0, "maxParallelism": 1},
                               accept_operation=True)
        refresh_id = response["operation_uri"].rstrip("/").split("/")[-1]
    if refresh_id:
        configured["last_refresh_id"] = refresh_id
        save_config(config)
        record(f"Started/monitoring SM_Sales refresh `{refresh_id}`.")
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            history = pbi.list(root + "/refreshes?$top=10")
            matches = [item for item in history if item.get("requestId") == refresh_id]
            if len(matches) > 1:
                raise ApiError("Duplicate model refresh IDs in history.")
            if matches:
                state = matches[0]["status"]
                print(f"SM_Sales refresh: {state}", flush=True)
                if state == "Completed":
                    configured["last_refresh_state"] = state
                    save_config(config)
                    break
                if state not in ("Unknown", "InProgress"):
                    raise ApiError(f"Model refresh {state}: "
                                   f"{matches[0].get('serviceExceptionJson')}. "
                                   "Configure credentials in the Fabric portal if required; no automatic retry.")
            time.sleep(10)
        else:
            raise TimeoutError("Model refresh has not completed within ten minutes; run ID persisted.")
    query = """EVALUATE ROW(
        "Actual hl", [Actual hl], "Forecast hl", [Forecast hl],
        "Deviation hl", [Deviation hl], "Deviation %", [Deviation %],
        "Revenue EUR", [Revenue EUR], "Margin EUR", [Margin EUR], "Margin %", [Margin %],
        "Rows", COUNTROWS('Sales vs Forecast'), "Calendar days", COUNTROWS('Date'),
        "Stage", SELECTEDVALUE('Sales vs Forecast'[Environment]))"""
    result = pbi.request("POST", root + "/executeQueries",
                         {"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}})
    if result.get("error") or len(result.get("results", [])) != 1:
        raise ApiError(f"Model query failed: {result.get('error')}.")
    entry = result["results"][0]
    if entry.get("error") or len(entry.get("tables", [])) != 1:
        raise ApiError(f"Model result failed: {entry.get('error')}.")
    table = entry["tables"][0]
    if table.get("error") or len(table.get("rows", [])) != 1:
        raise ApiError("Model query must return exactly one complete result row.")
    row = table["rows"][0]
    if row.get("[Rows]") != 10304 or row.get("[Calendar days]") != 730 or \
            row.get("[Stage]") != "dev" or Decimal(str(row.get("[Actual hl]"))) != Decimal("4488091.02"):
        raise ApiError("Model business-row count, calendar, environment or actual checksum differs.")
    measures = ("Actual hl", "Forecast hl", "Deviation hl", "Deviation %",
                "Revenue EUR", "Margin EUR", "Margin %")
    if not all(isinstance(row.get(f"[{name}]"), (int, float)) for name in measures):
        raise ApiError("All seven baseline measures must return numeric values for the baseline.")
    configured["baseline_query"] = row
    save_config(config)
    record(f"SM_Sales initial refresh and seven-measure live check PASS: `{json.dumps(row)}`.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="semantic-model-authoring")
    workspaces = [item for item in api.list("/v1/workspaces")
                  if item["displayName"] == stage["workspace_name"]]
    if len(workspaces) != 1 or workspaces[0]["id"] != stage["workspace_id"]:
        raise ContextError("Dev workspace resolution differs from configuration.")
    workspace_id = stage["workspace_id"]
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if workspaces[0].get("capacityId") != config["fabric"]["capacity_id"] or \
            len(capacities) != 1 or capacities[0]["state"] != "Active" or \
            capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("The model requires the approved existing Active F4 capacity.")
    curated = stage["items"]["LH_Curated"]
    security_api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
                       skill="e2e-medallion-architecture")
    roles = security_api.list(
        f"/v1/workspaces/{workspace_id}/items/{curated['id']}/dataAccessRoles")
    if len(roles) != 1 or roles[0]["name"] != "DefaultReader":
        raise ContextError("Curated OneLake baseline is not DefaultReader only; no role overwrite.")
    role = roles[0]
    rules = role["decisionRules"]
    permissions = {entry["attributeName"]: entry["attributeValueIncludedIn"]
                   for entry in rules[0]["permission"]} if len(rules) == 1 else {}
    members = {"fabricItemMembers": [{"sourcePath": f"{workspace_id}/{curated['id']}",
                                     "itemAccess": ["ReadAll"]}]}
    if permissions != {"Action": ["Read"], "Path": ["*"]} or \
            rules[0]["effect"] != "Permit" or role.get("members") != members:
        raise ContextError("Curated DefaultReader differs from the unrestricted initial baseline.")
    baseline = {"default_reader_id": role["id"], "baseline_verified": True}
    if not args.dry_run and curated.get("onelake_security") != baseline:
        curated["onelake_security"] = baseline
        save_config(config)
        record("LH_Curated OneLake baseline verified: only DefaultReader, Read on *, "
               "virtual ReadAll membership. Current OneLake documentation supplies this role "
               "by default; no extra enable payload or role overwrite. "
               "Skill: e2e-medallion-architecture; "
               "https://learn.microsoft.com/fabric/onelake/security/get-started-security; "
               "https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/list-data-access-roles.")
    folder = ROOT / "fabric" / "SM_Sales.SemanticModel"
    parts, digest = definition_parts(folder)
    matches = [item for item in api.list(f"/v1/workspaces/{workspace_id}/items?type=SemanticModel")
               if item["displayName"] == "SM_Sales"]
    configured = stage["items"].get("SM_Sales", {})
    if matches:
        if len(matches) != 1 or not (matches[0].get("description") or "").startswith(MARKER) or \
                configured.get("id") != matches[0]["id"] or \
                configured.get("definition_sha256") != digest:
            raise ContextError("Existing SM_Sales is conflicting or differs from the initial definition; "
                               "no overwrite of model or user-authored AI metadata.")
        item = matches[0]
    else:
        item = create_item(api, f"/v1/workspaces/{workspace_id}/semanticModels",
                           {"displayName": "SM_Sales", "description": MARKER + ": sales and forecasts.",
                            "definition": {"format": "TMDL", "parts": parts}}, args.dry_run)
        if args.dry_run:
            print("DRY-RUN: complete MCP-authored model; Automatic SSO, initial refresh and measure check.")
            return
        configured = stage["items"].setdefault("SM_Sales", {})
        configured.update({"id": item["id"], "type": "SemanticModel", "definition_sha256": digest})
        save_config(config)
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": "SM_Sales",
                         "description": MARKER + ": sales and forecasts."},
            "config": {"version": "2.0", "logicalId": str(uuid5(NAMESPACE_URL, "fabric-demo-platform/SM_Sales"))}}
        (folder / ".platform").write_text(json.dumps(platform, indent=2) + "\n", encoding="utf-8")
        record(f"Created complete MCP-authored SM_Sales `{item['id']}` from exported TMDL; "
               f"seven tables, seven measures, six relationships. Skill references: {REFERENCES}. "
               "Prep data for AI synonyms require user configuration through the supported UI; "
               "no persisted AI representation was authored.")
    connections_path = f"/v1/workspaces/{workspace_id}/items/{item['id']}/connections"
    references = api.list(connections_path)
    if len(references) != 1:
        raise ApiError("Expected exactly one OneLake data source reference.")
    reference = references[0]
    details = reference["connectionDetails"]
    if stage["items"]["LH_Curated"]["id"] not in details["path"]:
        raise ContextError("Model data source does not reference the owned Curated lakehouse.")
    if reference["connectivityType"] != "Automatic":
        if reference["connectivityType"] != "None":
            raise ContextError("An existing non-SSO connection must not be replaced automatically.")
        api.request("POST", f"/v1/workspaces/{workspace_id}/semanticModels/{item['id']}/bindConnection",
                    {"connectionBinding": {"connectivityType": "Automatic",
                                           "connectionDetails": details}}, dry_run=args.dry_run)
        if not args.dry_run:
            references = api.list(connections_path)
    if not args.dry_run:
        if len(references) != 1 or references[0]["connectivityType"] != "Automatic":
            raise ApiError("Automatic end-user SSO binding did not persist.")
        configured["connection_binding"] = references[0]
        save_config(config)
        record("SM_Sales Automatic end-user SSO binding verified; no fixed-identity connection.")
    if args.refresh and not args.dry_run:
        pbi = Api("https://api.powerbi.com", config["tenant"]["id"], skill="semantic-model-authoring")
        refresh_and_check(pbi, f"/v1.0/myorg/groups/{workspace_id}/datasets/{item['id']}",
                          configured, config)


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError) as error:
        record(f"Sales model bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
