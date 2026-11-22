"""Create only the owned Dev raw-file and mirrored Gold schema shortcuts."""

import argparse
import sys
from urllib.parse import unquote, urlparse

from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError
from upload_sharepoint import graph_credential

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    workspace_id = stage["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="spark-cli")
    capacity = [item for item in api.list("/v1/capacities")
                if item["id"] == config["fabric"]["capacity_id"]]
    workspace = api.request("GET", f"/v1/workspaces/{workspace_id}")
    if len(capacity) != 1 or capacity[0]["state"] != "Active" or \
            capacity[0]["sku"] != config["cost_guardrails"]["fabric_sku"] or \
            workspace["capacityId"] != capacity[0]["id"]:
        raise ContextError("Dev shortcuts require the unchanged approved Active capacity.")

    def no_prompt(uri, code, expires):
        raise ContextError("SharePoint cached authentication expired; human device sign-in is required.")

    graph = Api("https://graph.microsoft.com", config["tenant"]["id"],
                credential=graph_credential(config, no_prompt))
    relative = stage["sharepoint_folder"] + "/raw"
    folder = graph.request("GET", f"/v1.0/drives/{config['sharepoint']['drive_id']}/root:/{relative}")
    site_url = config["sharepoint"]["site_url"].rstrip("/")
    actual_url = urlparse(folder["webUrl"])
    site = urlparse(site_url)
    if actual_url.netloc.casefold() != site.netloc.casefold() or \
            not unquote(actual_url.path).startswith(site.path.rstrip("/") + "/"):
        raise ContextError("Actual raw source URL does not belong to the configured DemoData site.")
    subpath = unquote(actual_url.path)[len(site.path.rstrip("/")):]
    if "folder" not in folder:
        raise ContextError("Raw forecast source is not a folder.")
    plans = [
        ("LH_Landing", {"path": "Files", "name": "raw_forecasts",
                        "target": {"oneDriveSharePoint": {
                            "location": site_url, "subpath": subpath,
                            "connectionId": config["fabric"]["connections"]["sharepoint"]["id"],
                            "updateFabricItemSensitivity": False}}}),
        ("LH_Curated", {"path": "Tables", "name": "gold",
                        "target": {"oneLake": {"workspaceId": workspace_id,
                                              "itemId": stage["items"]["MIR_UC_Gold"]["id"],
                                              "path": "Tables/gold"}}}),
    ]
    if stage["items"].get("NB_Clean_Forecast", {}).get("last_run_state") == "Completed":
        plans.append(("LH_Curated", {"path": "Tables/dbo", "name": "forecast_clean",
                                    "target": {"oneLake": {
                                        "workspaceId": workspace_id,
                                        "itemId": stage["items"]["LH_Landing"]["id"],
                                        "path": "Tables/forecast/forecast_clean"}}}))
    for lakehouse, plan in plans:
        lakehouse_id = stage["items"][lakehouse]["id"]
        detail = api.request("GET", f"/v1/workspaces/{workspace_id}/lakehouses/{lakehouse_id}")
        if detail["properties"].get("defaultSchema") != "dbo":
            raise ApiError("Schema-enabled lakehouse is required for the configured shortcuts.")
        endpoint = f"/v1/workspaces/{workspace_id}/items/{lakehouse_id}/shortcuts"
        matches = [item for item in api.list(endpoint)
                   if item["path"].strip("/") == plan["path"] and item["name"] == plan["name"]]
        if matches:
            target_key = next(iter(plan["target"]))
            target = matches[0].get("target", {}).get(target_key, {})
            expected_target = plan["target"][target_key]
            if target_key == "oneDriveSharePoint":
                expected_uri = expected_target["location"].rstrip("/") + "/" + expected_target["subpath"].lstrip("/")
                actual_uri = target.get("location", "").rstrip("/") + "/" + target.get("subpath", "").lstrip("/")
                same_target = unquote(actual_uri).rstrip("/") == unquote(expected_uri).rstrip("/") and \
                    target.get("connectionId") == expected_target["connectionId"] and \
                    target.get("updateFabricItemSensitivity") == expected_target["updateFabricItemSensitivity"]
            else:
                same_target = all(target.get(key) == value for key, value in expected_target.items()
                                  if key != "path") and target.get("path", "").strip("/") == expected_target["path"].strip("/")
            if len(matches) != 1 or not same_target:
                raise ContextError("Existing shortcut target differs; no overwrite of unowned bindings.")
        else:
            # Skill common/COMMON-CORE.md OneLake Shortcuts; official Create Shortcut (Abort).
            api.request("POST", endpoint + "?shortcutConflictPolicy=Abort", plan, dry_run=args.dry_run)
        if args.dry_run:
            continue
        matches = [item for item in api.list(endpoint)
                   if item["path"].strip("/") == plan["path"] and item["name"] == plan["name"]]
        if len(matches) != 1:
            raise ApiError("Shortcut creation read-back is missing/ambiguous.")
        key = plan["path"] + "/" + plan["name"]
        stage["items"][lakehouse].setdefault("shortcuts", {})[key] = matches[0]
        save_config(config)
        record(f"Dev `{lakehouse}/{key}` shortcut target read-back PASS. Skill: common/COMMON-CORE.md OneLake Shortcuts and Create Shortcut REST spec.")
        print(f"PASS {lakehouse}/{key}")
    print("DRY-RUN shortcut plan complete." if args.dry_run else
          "Raw and Gold shortcuts ready; Excel transformation requires its documented preview configuration.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Shortcut bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
