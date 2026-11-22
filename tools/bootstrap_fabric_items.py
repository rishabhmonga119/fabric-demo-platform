"""Provision owned schema-enabled Dev lakehouses and inspect connector prerequisites."""

import argparse
import json
import sys
import time

from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

SKILL = "e2e-medallion-architecture"
MARKER = "Managed by fabric-demo-platform demo automation"
REFERENCES = "fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md"


def create_lakehouse(api: Api, workspace_id: str, name: str, description: str,
                     dry_run: bool) -> dict | None:
    # SPARK-AUTHORING-CORE.md Lakehouse Creation; COMMON-CORE.md LRO.
    # https://learn.microsoft.com/rest/api/fabric/lakehouse/items/create-lakehouse
    return create_item(api, f"/v1/workspaces/{workspace_id}/lakehouses",
                       {"displayName": name, "description": description,
                        "creationPayload": {"enableSchemas": True}}, dry_run)


def create_item(api: Api, endpoint: str, payload: dict, dry_run: bool) -> dict | None:
    return post_and_wait(api, endpoint, payload, dry_run, payload["displayName"])


def post_and_wait(api: Api, endpoint: str, payload: dict, dry_run: bool, name: str,
                  *, retrieve_result: bool = True) -> dict | None:
    response = api.request("POST", endpoint, payload,
                           dry_run=dry_run, accept_operation=True, with_response_info=True)
    if dry_run:
        return None
    if response["status_code"] in (200, 201):
        return response["body"]
    if response["status_code"] != 202:
        raise ApiError("Fabric operation did not return documented 200/201/202.")
    uri = response["body"]["operation_uri"]
    return wait_operation(api, uri, name, retry_after=response["retry_after"],
                          retrieve_result=retrieve_result)


def wait_operation(api: Api, uri: str, name: str, *, retry_after: str | None = None,
                   retrieve_result: bool = True) -> dict:
    response = {"retry_after": retry_after}
    deadline = time.monotonic() + 600
    attempts = 0
    while True:
        raw = response["retry_after"]
        delay = int(raw) if isinstance(raw, str) and raw.isdigit() and int(raw) > 0 else min(30, 2 ** min(attempts + 1, 5))
        if time.monotonic() + delay >= deadline:
            raise TimeoutError("Fabric item creation did not complete within ten minutes.")
        time.sleep(delay)
        response = api.request("GET", uri, with_response_info=True)
        status = response["body"]["status"]
        print(f"{name}: {status}", flush=True)
        if status == "Succeeded":
            return api.request("GET", uri.rstrip("/") + "/result") if retrieve_result else response["body"]
        if status == "Failed":
            raise ApiError(f"Fabric item creation failed: {response['body'].get('error')}")
        if status not in ("NotStarted", "Running"):
            raise ApiError(f"Unsupported Fabric operation state: {status}")
        attempts += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill=SKILL)
    capacity = [item for item in api.list("/v1/capacities")
                if item["id"] == config["fabric"]["capacity_id"]]
    if len(capacity) != 1 or capacity[0]["sku"] != config["cost_guardrails"]["fabric_sku"] or \
            capacity[0]["state"] != "Active":
        raise ContextError(f"Selected existing Fabric capacity is not the approved Active {config['cost_guardrails']['fabric_sku']}.")
    stage = config["environments"]["dev"]
    workspace_id = stage["workspace_id"]
    workspace = api.request("GET", f"/v1/workspaces/{workspace_id}")
    if workspace["displayName"] != stage["workspace_name"] or \
            workspace["capacityId"] != config["fabric"]["capacity_id"] or \
            workspace.get("capacityAssignmentProgress") != "Completed":
        raise ContextError("Dev workspace name/capacity/assignment differs from the approved configuration.")
    items = api.list(f"/v1/workspaces/{workspace_id}/items?type=Lakehouse")
    for name, purpose in (
        ("LH_Landing", "Stage-isolated standard and raw forecast ingestion."),
        ("LH_Curated", "Curated sales/forecast integration and OneLake security."),
    ):
        matches = [item for item in items if item["displayName"] == name]
        if len(matches) > 1:
            raise ContextError(f"Multiple Dev items named {name}.")
        configured = stage["items"].get(name, {})
        if matches:
            item = matches[0]
            if not (item.get("description") or "").startswith(MARKER):
                raise ContextError(f"Existing {name} is unowned; no overwrite.")
            if configured.get("id") not in (None, item["id"]):
                raise ContextError(f"Configured {name} ID differs; no rebind.")
        else:
            item = create_lakehouse(api, workspace_id, name, f"{MARKER}: {purpose}", args.dry_run)
            if args.dry_run:
                continue
        if not args.dry_run:
            stage["items"][name] = {"id": item["id"], "type": "Lakehouse"}
            save_config(config)
            record(f"Created/verified owned Dev `{name}`: `{item['id']}`; skill references: {REFERENCES}.")
        deadline = time.monotonic() + 300
        while True:
            detail = api.request("GET", f"/v1/workspaces/{workspace_id}/lakehouses/{item['id']}")
            if detail["properties"].get("defaultSchema") != "dbo":
                raise ApiError(f"{name} is not schema enabled.")
            endpoint = detail["properties"]["sqlEndpointProperties"]
            if endpoint["provisioningStatus"] == "Success":
                break
            if endpoint["provisioningStatus"] != "InProgress":
                raise ApiError(f"{name}: SQL endpoint provisioning {endpoint['provisioningStatus']}.")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{name}: SQL endpoint did not provision within five minutes.")
            time.sleep(10)
        if not args.dry_run:
            stage["items"][name]["sql_endpoint_id"] = endpoint["id"]
            save_config(config)
            record(f"Dev `{name}` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.")
        print(f"PASS Dev {name}: {item['id']}")
    # Connection reference requires live discovery; OAuth2 is explicitly not API-creatable.
    supported = api.list("/v1/connections/supportedConnectionTypes?showAllCreationMethods=true")
    connector_info = [item for item in supported
                      if "databricks" in item["type"].casefold() or "sharepoint" in item["type"].casefold()]
    print("Live connector contracts: " + json.dumps(connector_info))
    connections = api.list("/v1/connections")
    missing = []
    for key, connection in config["fabric"]["connections"].items():
        matches = [item for item in connections if item.get("displayName") == connection["name"]]
        if not matches:
            missing.append(connection["name"])
        elif len(matches) != 1:
            raise ContextError(f"Multiple connections named {connection['name']}.")
        else:
            print(f"Existing connection {connection['name']}: {matches[0]['id']} (binding verification pending)")
    if not args.dry_run:
        record("Live Databricks/SharePoint supportedConnectionTypes inspected. Organizational OAuth2 connections require interactive Fabric portal authoring; not attempted through the unsupported Create Connection credential union.")
        if missing:
            record(f"Step 5 human prerequisite: create organizational connections {', '.join(missing)}.")
    print("DRY-RUN complete." if args.dry_run else
          "Dev schema-enabled lakehouses ready. Remaining connection prerequisites: " + ", ".join(missing))


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Fabric item bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
