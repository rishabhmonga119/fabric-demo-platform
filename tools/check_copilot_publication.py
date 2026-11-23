"""Check Prod Copilot prerequisites without publishing agents or changing access."""

import argparse
from datetime import datetime, timezone
import json
import sys

from bootstrap_entra import has_membership
from capacity_guard import verify_stage_capacity
from check_demo_licenses import license_features
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = (
    "fabric-skills/common/COMMON-CORE.md; "
    "https://learn.microsoft.com/rest/api/fabric/dataagent/items/get-data-agent; "
    "https://learn.microsoft.com/rest/api/fabric/core/workspaces/list-workspace-role-assignments; "
    "https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot; "
    "https://learn.microsoft.com/fabric/iq/connectors/agent-builder-overview"
)


def inspect_model_access(config: dict, stage: dict, api: Api) -> None:
    workspace = stage["workspace_id"]
    model_id = stage["items"]["SM_Sales"]["id"]
    pbi = Api("https://api.powerbi.com", config["tenant"]["id"],
              skill="semantic-model-authoring")
    model = pbi.request("GET", f"/v1.0/myorg/groups/{workspace}/datasets/{model_id}")
    connections = api.list(f"/v1/workspaces/{workspace}/items/{model_id}/connections")
    print(json.dumps({"model": "SM_Sales",
                      "isOnPremGatewayRequired": model.get("isOnPremGatewayRequired"),
                      "connections": connections}))
    relevant = {config["entra"]["groups"][key]["id"] for key in ("sales_north", "sales_south")}
    relevant.update(user["id"] for user in config["entra"]["users"].values())
    admin = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
                skill="onelake-catalog-cli")
    for name in ("LH_Curated", "MIR_UC_Gold"):
        item = stage["items"][name]
        roles = api.list(f"/v1/workspaces/{workspace}/items/{item['id']}/dataAccessRoles")
        access = admin.list(f"/v1/admin/workspaces/{workspace}/items/{item['id']}/users",
                            field="accessDetails")
        selected = [{"principal_id": entry["principal"]["id"],
                     "access": entry["itemAccessDetails"]} for entry in access
                    if entry["principal"]["id"] in relevant]
        print(json.dumps({"item": name, "roles": roles, "configured_sales_principal_access": selected}))
    print("DIAGNOSTIC ONLY: administrator metadata is not a successful viewer-session query. "
          "Direct Lake SSO requires source OneLake access as well as model/report Read. "
          "No access grants or connection changes were made.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Check live prerequisites without saving local checkpoint results.")
    parser.add_argument("--model-access-only", action="store_true",
                        help="Inspect model source and existing OneLake grants without querying as the viewer.")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Copilot publication prerequisites require the DEMO administrator.")
    verify_context()
    config = load_config()
    stage = config["environments"]["prod"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    root = f"/v1/workspaces/{stage['workspace_id']}"
    verify_stage_capacity(api, config, api.request("GET", root), stage)
    if args.model_access_only:
        inspect_model_access(config, stage, api)
        if not args.dry_run:
            record("Step 7 read-only model-access diagnostic completed: checked the cloud "
                   "source/gateway flag, OneLake roles and configured sales-principal item "
                   "grants. This is not a viewer-session success or permission change. "
                   "References: semantic-model-authoring/references/connection-binding.md; "
                   "onelake-catalog-cli/references/admin-audit.md; "
                   "https://learn.microsoft.com/rest/api/fabric/admin/items/list-item-access-details; "
                   "https://learn.microsoft.com/fabric/fundamentals/direct-lake-security-integration.")
        return
    items = api.list(root + "/items")
    for name in ("DA_Sales", "ONT_Business", "SM_Sales", "RPT_Sales"):
        expected = stage["items"][name]
        matches = [item for item in items
                   if item["displayName"] == name and item["type"] == expected["type"]]
        if len(matches) != 1 or matches[0]["id"] != expected["id"]:
            raise ContextError(f"Prod {name} differs from the verified deployment.")
    agent = api.request("GET", root + f"/dataAgents/{stage['items']['DA_Sales']['id']}")
    if not agent.get("properties", {}).get("publishedDescription"):
        raise ContextError("Prod DA_Sales is not published to its Fabric runtime.")
    assignments = api.list(root + "/roleAssignments")
    graph = Api("https://graph.microsoft.com", config["tenant"]["id"])
    accounts = [config["tenant"]["admin_upn"]]
    for key in ("north", "south"):
        user = config["entra"]["users"][key]
        group = config["entra"]["groups"]["sales_" + key]
        roles = [item for item in assignments if item["principal"]["id"] == group["id"]]
        if len(roles) != 1 or roles[0]["role"] != "Viewer":
            raise ContextError(f"{group['name']} does not have the expected Prod Viewer role.")
        if not has_membership(graph, group["id"], user["id"]):
            raise ContextError(f"The configured {key} viewer is not in its approved sales group.")
        accounts.append(user["upn"])
        print(f"PASS: {key} sales-group membership and Prod Viewer role; no access grants.")
    for account in accounts:
        plans = set()
        for licence in graph.list(f"/v1.0/users/{account}/licenseDetails"):
            plans.update(plan["servicePlanName"] for plan in licence["servicePlans"]
                         if plan["provisioningStatus"] == "Success")
        features = license_features(plans)
        if not features["power_bi_pro"] or not features["m365_copilot"]:
            raise ContextError("A configured presenter/viewer lacks enabled Power BI/Copilot plans; "
                               "licence assignment requires a human.")
    print("PASS: existing presenter/viewer Power BI and Copilot licence plans.")
    print("HUMAN CHECKPOINT: Publish to Microsoft Copilot, M365/Teams pinning, Sales Assistant "
          "creation/sharing and a real viewer-session answer are not verified by these APIs.")
    if not args.dry_run:
        checkpoint = config.setdefault("copilot", {}).setdefault("step7", {})
        checkpoint.update({
            "workspace_id": stage["workspace_id"],
            "data_agent_id": agent["id"],
            "prerequisites_checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fabric_runtime_published": True,
            "viewer_groups_and_licence_plans_verified": True,
        })
        for key in ("microsoft_copilot_publication_verification", "teams_verification",
                    "sales_assistant_verification", "north_viewer_answer_verification"):
            checkpoint.setdefault(key, "pending-human")
        save_config(config)
        record("Step 7 prerequisite Check PASS: Prod identities/Active F4, Fabric-runtime "
               "publication, existing sales-group Viewer memberships and enabled "
               "Power BI/Copilot plans. No cloud writes, grants, licences or duplicate "
               "agent publication. Microsoft Copilot/Teams/Agent Builder/viewer-session checks "
               f"require the human checkpoint. References: {REFERENCES}.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        record(f"Step 7 prerequisite check blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
