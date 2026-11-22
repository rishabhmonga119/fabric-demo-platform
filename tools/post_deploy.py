"""Bind stage-local shortcuts and verify the ingestion metadata before the first run."""

import argparse
from copy import deepcopy
import json
import sys
from urllib.parse import unquote

from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def same_target(actual: dict, expected: dict) -> bool:
    key = next(iter(expected))
    actual, expected = actual.get(key, {}), expected[key]
    if key == "oneDriveSharePoint":
        def uri(value):
            return unquote(value.get("location", "").rstrip("/") + "/" +
                           value.get("subpath", "").lstrip("/")).rstrip("/")
        return uri(actual) == uri(expected) and actual.get("connectionId") == expected["connectionId"]
    return actual.get("workspaceId") == expected["workspaceId"] and \
        actual.get("itemId") == expected["itemId"] and \
        actual.get("path", "").strip("/") == expected["path"].strip("/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("test", "prod"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-prod", action="store_true")
    args = parser.parse_args()
    verify_context()
    if args.stage == "prod" and not args.approved_prod:
        raise ContextError("Production binding requires the approval gate.")
    config = load_config()
    stage = config["environments"][args.stage]
    workspace_id = stage["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="spark-cli")
    workspace = api.request("GET", f"/v1/workspaces/{workspace_id}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if workspace["displayName"] != stage["workspace_name"] or \
            workspace["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Stage binding target differs from the approved existing Active F4.")
    source = json.loads((ROOT / "fabric" / "LH_Landing.Lakehouse" / "shortcuts.metadata.json").read_text())
    raw = [item for item in source if item["name"] == "raw_forecasts"]
    if len(raw) != 1:
        raise ContextError("The captured raw shortcut is missing/ambiguous.")
    target = deepcopy(raw[0]["target"]["oneDriveSharePoint"])
    target["subpath"] = target["subpath"].replace("Forecasts/Dev", stage["sharepoint_folder"])
    target["updateFabricItemSensitivity"] = False
    plans = [
        ("LH_Landing", {"path": "Files", "name": "raw_forecasts",
                        "target": {"oneDriveSharePoint": target}}),
        ("LH_Curated", {"path": "Tables", "name": "gold", "target": {"oneLake": {
            "workspaceId": workspace_id, "itemId": stage["items"]["MIR_UC_Gold"]["id"], "path": "Tables/gold"}}})]
    if stage["items"]["PL_Refresh"].get("last_run_state") == "Completed":
        plans.append(("LH_Curated", {"path": "Tables/dbo", "name": "forecast_clean",
                                    "target": {"oneLake": {"workspaceId": workspace_id,
                                        "itemId": stage["items"]["LH_Landing"]["id"],
                                        "path": "Tables/forecast/forecast_clean"}}}))
    for name, plan in plans:
        root = f"/v1/workspaces/{workspace_id}/items/{stage['items'][name]['id']}/shortcuts"
        matches = [item for item in api.list(root)
                   if item["name"] == plan["name"] and item["path"].strip("/") == plan["path"]]
        if matches and (len(matches) != 1 or not same_target(matches[0]["target"], plan["target"])):
            raise ContextError("An existing shortcut has a different target; no overwrite.")
        if not matches:
            api.request("POST", root + "?shortcutConflictPolicy=Abort", plan, dry_run=args.dry_run)
        if not args.dry_run:
            matches = [item for item in api.list(root)
                       if item["name"] == plan["name"] and item["path"].strip("/") == plan["path"]]
            if len(matches) != 1 or not same_target(matches[0]["target"], plan["target"]):
                raise ApiError("Stage-local shortcut target did not persist.")
            stage["items"][name].setdefault("shortcuts", {})[plan["path"] + "/" + plan["name"]] = matches[0]
            save_config(config)
            record(f"{args.stage} {name}/{plan['name']} target binding PASS; "
                   "reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.")
    settings = api.request("GET", f"/v1/workspaces/{workspace_id}/spark/settings")
    if settings["pool"]["defaultPool"]["name"] != "Starter Pool" or settings["environment"].get("name"):
        raise ContextError("The stage must use the default Starter Pool with no custom Environment.")
    vl = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="variable-library-cli")
    library_path = f"/v1/workspaces/{workspace_id}/variableLibraries/{stage['items']['VL_Config']['id']}"
    state = vl.request("GET", library_path)
    if state["properties"]["activeValueSetName"] != args.stage:
        vl.request("PATCH", library_path, {"properties": {"activeValueSetName": args.stage}},
                   dry_run=args.dry_run)
        if not args.dry_run:
            state = vl.request("GET", library_path)
            if state["properties"]["activeValueSetName"] != args.stage:
                raise ApiError("Stage Variable Library active value set did not persist.")
    if not args.dry_run:
        stage["items"]["VL_Config"]["active_value_set"] = args.stage
        save_config(config)
        record(f"{args.stage} ingestion metadata ready: stage shortcuts, Starter Pool/no custom "
               "Environment, active Variable Library value set verified. Excel preview standard "
               "transformation must be created in the UI if absent; no unsupported payload.")
    print(f"{args.stage} post-deploy metadata {'dry-run' if args.dry_run else 'PASS'}")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        record(f"Stage post-deploy binding blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
