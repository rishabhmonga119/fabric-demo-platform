"""Check Prod Copilot prerequisites without publishing agents or changing access."""

import argparse
from datetime import datetime, timezone
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Check live prerequisites without saving local checkpoint results.")
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
    print("HUMAN CHECKPOINT: Agent Store publication, M365/Teams pinning, Sales Assistant "
          "creation/sharing and a real viewer-session answer are not verified by these APIs.")
    if not args.dry_run:
        config.setdefault("copilot", {})["step7"] = {
            "workspace_id": stage["workspace_id"],
            "data_agent_id": agent["id"],
            "prerequisites_checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fabric_runtime_published": True,
            "viewer_groups_and_licence_plans_verified": True,
            "agent_store_verification": "pending-human",
            "teams_verification": "pending-human",
            "sales_assistant_verification": "pending-human",
            "north_viewer_answer_verification": "pending-human",
        }
        save_config(config)
        record("Step 7 prerequisite Check PASS: Prod identities/Active F4, Fabric-runtime "
               "publication, existing sales-group Viewer memberships and enabled "
               "Power BI/Copilot plans. No cloud writes, grants, licences or duplicate "
               "agent publication. Agent Store/Teams/Agent Builder/viewer-session checks "
               f"require the human checkpoint. References: {REFERENCES}.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        record(f"Step 7 prerequisite check blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
