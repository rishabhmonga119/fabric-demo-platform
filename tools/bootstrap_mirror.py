"""Create a stage-isolated Gold mirrored catalog; Dev also verifies connection sharing."""

import argparse
from base64 import b64decode, b64encode
import json
import sys

from bootstrap_fabric_items import MARKER, create_item, post_and_wait
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/mirroredAzureDatabricksCatalog/definition/mirroredAzureDatabricksCatalogDefinition/1.0.0/schema.json"
TYPE = "MirroredAzureDatabricksCatalog"


def mirror_definition(catalog: str, connection_id: str) -> dict:
    return {"$schema": SCHEMA, "catalogName": catalog,
            "databricksWorkspaceConnectionId": connection_id, "autoSync": "Enabled",
            "mirroringMode": "Partial",
            "mirrorConfiguration": {"schemas": [{"name": "gold", "mirroringMode": "Full"}]}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stage", choices=("dev", "test", "prod"), default="dev")
    parser.add_argument("--approved-prod", action="store_true")
    args = parser.parse_args()
    verify_context()
    if args.stage == "prod" and not args.approved_prod:
        raise ContextError("Explicit production deployment approval is required.")
    config = load_config()
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="sqldw-cli")
    connections = api.list("/v1/connections")
    principal = config["entra"]["application"]["service_principal_id"]
    for key, connection in (config["fabric"]["connections"].items() if args.stage == "dev" else []):
        matches = [item for item in connections if item.get("displayName") == connection["name"]]
        if len(matches) != 1:
            raise ContextError(f"Expected one user-created connection {connection['name']}.")
        item = matches[0]
        expected_type = "AzureDatabricksWorkspace" if key == "databricks" else "SharePoint"
        expected_url = config["azure"]["databricks_workspace_url"] if key == "databricks" else config["sharepoint"]["site_url"]
        if item["connectivityType"] != "ShareableCloud" or \
                item["connectionDetails"]["type"] != expected_type or \
                item["connectionDetails"]["path"].rstrip("/").casefold() != expected_url.rstrip("/").casefold() or \
                item["credentialDetails"]["credentialType"] != "OAuth2":
            raise ContextError(f"{connection['name']} type/URL/shareability/authentication differs.")
        if connection["id"] not in (None, item["id"]):
            raise ContextError(f"{connection['name']} ID differs; no rebind.")
        assignments = api.list(f"/v1/connections/{item['id']}/roleAssignments")
        granted = [assignment for assignment in assignments
                   if assignment["principal"]["id"] == principal]
        if not granted:
            # COMMON-CORE.md role patterns; official Add Connection Role Assignment.
            api.request("POST", f"/v1/connections/{item['id']}/roleAssignments",
                        {"principal": {"id": principal, "type": "ServicePrincipal"}, "role": "User"},
                        dry_run=args.dry_run)
        elif len(granted) != 1 or granted[0]["role"] not in ("User", "UserWithReshare", "Owner"):
            raise ContextError("Unexpected CI/CD connection role; no overwrite.")
        if not args.dry_run:
            assignments = api.list(f"/v1/connections/{item['id']}/roleAssignments")
            if not any(assignment["principal"]["id"] == principal and
                       assignment["role"] in ("User", "UserWithReshare", "Owner")
                       for assignment in assignments):
                raise ApiError("CI/CD connection User access read-back failed.")
            connection["id"] = item["id"]
            save_config(config)
            record(f"Verified user-created `{connection['name']}` connection `{item['id']}` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.")
    stage = config["environments"][args.stage]
    if stage["databricks_catalog"] != "demo_" + args.stage:
        raise ContextError("Mirror catalog differs from the fixed stage binding.")
    workspace_id = stage["workspace_id"]
    workspace = api.request("GET", f"/v1/workspaces/{workspace_id}")
    capacity = [item for item in api.list("/v1/capacities") if item["id"] == config["fabric"]["capacity_id"]]
    if workspace["capacityId"] != config["fabric"]["capacity_id"] or len(capacity) != 1 or \
            capacity[0]["sku"] != config["cost_guardrails"]["fabric_sku"] or capacity[0]["state"] != "Active":
        raise ContextError(f"Mirror workspace/capacity differs from approved Active {config['cost_guardrails']['fabric_sku']}.")
    name = "MIR_UC_Gold"
    matches = [item for item in api.list(f"/v1/workspaces/{workspace_id}/items?type={TYPE}")
               if item["displayName"] == name]
    configured = stage["items"].get(name, {})
    if matches:
        if len(matches) != 1 or matches[0]["type"] != TYPE or \
                not (matches[0].get("description") or "").startswith(MARKER) or \
                configured.get("id") not in (None, matches[0]["id"]):
            raise ContextError("Existing mirror is unowned/conflicting; no overwrite.")
        item = matches[0]
    else:
        connection_id = next(connection["id"] for connection in connections
                             if connection.get("displayName") == config["fabric"]["connections"]["databricks"]["name"])
        definition = mirror_definition(stage["databricks_catalog"], connection_id)
        # ITEM-DEFINITIONS-CORE.md Other Item Types; mirrored-azuredatabricks-unitycatalog-definition.
        payload = {"displayName": name, "type": TYPE,
                   "description": f"{MARKER}: {args.stage.title()} Unity Catalog Gold only; future Gold changes auto-sync.",
                   "definition": {"parts": [{"path": "definition.json", "payloadType": "InlineBase64",
                                             "payload": b64encode(json.dumps(definition).encode()).decode()}]}}
        item = create_item(api, f"/v1/workspaces/{workspace_id}/items", payload, args.dry_run)
        if args.dry_run:
            print("DRY-RUN: Gold-only mirror and scoped connection-sharing plan complete.")
            return
    if not args.dry_run:
        stage["items"][name] = {"id": item["id"], "type": TYPE}
        save_config(config)
        endpoints = [endpoint for endpoint in api.list(f"/v1/workspaces/{workspace_id}/items?type=SQLEndpoint")
                     if endpoint["displayName"] == name]
        if len(endpoints) != 1:
            raise ApiError("Mirrored catalog requires one matching auto-provisioned SQL endpoint.")
        stage["items"][name]["sql_endpoint_id"] = endpoints[0]["id"]
        save_config(config)
        detail = api.request("GET", f"/v1/workspaces/{workspace_id}/items/{item['id']}")
        if detail["displayName"] != name or detail["type"] != TYPE:
            raise ApiError("Mirrored catalog identity read-back differs.")
        definition_result = post_and_wait(
            api, f"/v1/workspaces/{workspace_id}/items/{item['id']}/getDefinition",
            {}, False, "MIR_UC_Gold definition")
        parts = definition_result["definition"]["parts"]
        source = [part for part in parts if part["path"] == "definition.json"]
        if len(source) != 1 or source[0]["payloadType"] != "InlineBase64":
            raise ApiError("Mirror definition requires exactly one inline definition.json part.")
        actual = json.loads(b64decode(source[0]["payload"], validate=True))
        expected = mirror_definition(stage["databricks_catalog"], config["fabric"]["connections"]["databricks"]["id"])
        if any(actual.get(field) != expected[field] for field in
               ("catalogName", "databricksWorkspaceConnectionId", "autoSync", "mirroringMode", "mirrorConfiguration")):
            raise ApiError("Mirror source binding or Gold-only/future-schema sync configuration differs.")
        record(f"Created/verified `{name}`: `{item['id']}`, catalog `{stage['databricks_catalog']}`, gold only, autoSync Enabled. Skill: common/ITEM-DEFINITIONS-CORE.md Other Item Types and its mirrored Azure Databricks definition spec. Data-table verification pending.")
        print(f"Mirror created: {item['id']}; verify populated Gold tables next.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Mirror bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
