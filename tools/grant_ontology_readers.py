"""Grant the two approved sales groups Read+Build on Prod SM_Sales only."""

import argparse
from datetime import datetime, timezone
import sys

from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = (
    "semantic-model-authoring/references/semantic-model-rest-api.md, Permissions; "
    "https://learn.microsoft.com/fabric/iq/ontology/how-to-generate-from-semantic-models; "
    "https://learn.microsoft.com/rest/api/power-bi/datasets/put-dataset-user-in-group; "
    "https://learn.microsoft.com/rest/api/power-bi/datasets/post-dataset-user-in-group"
)


def permission_plan(users: list[dict], groups: list[dict]) -> list[tuple[str, dict]]:
    plan = []
    for group in groups:
        matches = [user for user in users if user["identifier"] == group["id"]]
        if len(matches) > 1 or matches and matches[0]["principalType"] != "Group":
            raise ContextError(f"Ambiguous dataset principal for {group['name']}; no overwrite.")
        if matches:
            right = matches[0]["datasetUserAccessRight"]
            if right == "ReadExplore":
                continue
            if right != "Read":
                raise ContextError(f"Unexpected {right} permission for {group['name']}; no overwrite.")
        plan.append(("PUT" if matches else "POST", {
            "identifier": group["id"],
            "principalType": "Group",
            "datasetUserAccessRight": "ReadExplore",
        }))
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-prod-ontology-build", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Metadata CI cannot grant semantic-model access.")
    verify_context()
    if not args.dry_run and not args.approved_prod_ontology_build:
        raise ContextError("Explicit approval of both Prod ontology reader Build grants is required.")
    config = load_config()
    stage = config["environments"]["prod"]
    workspace = stage["workspace_id"]
    model = stage["items"]["SM_Sales"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="semantic-model-authoring")
    root = f"/v1/workspaces/{workspace}"
    verify_stage_capacity(api, config, api.request("GET", root), stage)
    actual = [item for item in api.list(root + "/items?type=SemanticModel")
              if item["displayName"] == "SM_Sales"]
    if len(actual) != 1 or actual[0]["id"] != model["id"]:
        raise ContextError("Prod SM_Sales differs from the approved target.")
    groups = [config["entra"]["groups"][key] for key in ("sales_north", "sales_south")]
    assignments = api.list(root + "/roleAssignments")
    for group in groups:
        roles = [entry["role"] for entry in assignments
                 if entry["principal"]["id"] == group["id"]]
        if roles != ["Viewer"]:
            raise ContextError(f"{group['name']} no longer has the approved Prod Viewer role.")
    pbi = Api("https://api.powerbi.com", config["tenant"]["id"],
              skill="semantic-model-authoring")
    endpoint = f"/v1.0/myorg/groups/{workspace}/datasets/{model['id']}/users"
    plan = permission_plan(pbi.list(endpoint), groups)
    for method, payload in plan:
        pbi.request(method, endpoint, payload, dry_run=args.dry_run)
        if not args.dry_run:
            record(f"Approved Step 7 ontology reader {method}: Prod SM_Sales "
                   f"({model['id']}), group {payload['identifier']}, ReadExplore. "
                   "No Write/Reshare or workspace-role change.")
    if args.dry_run:
        print(f"DRY-RUN: {len(plan)} Read+Build grant(s), only the two approved groups "
              "on Prod SM_Sales. No configuration or log writes.")
        return
    persisted = pbi.list(endpoint)
    if permission_plan(persisted, groups):
        raise ApiError("Both approved Read+Build grants are not visible in readback; "
                       "permission propagation or further read-only inspection is required.")
    for group in groups:
        print(f"PASS: {group['name']} ({group['id']}) = ReadExplore on Prod SM_Sales.")
    checkpoint = config.setdefault("copilot", {}).setdefault("step7", {})
    checkpoint["viewer_ontology_build_grant"] = "verified-prod-sm-sales-read-build"
    checkpoint.setdefault("viewer_ontology_build_granted_at",
                          datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not checkpoint.get("north_viewer_data_agent_verification", "").startswith("user-confirmed"):
        checkpoint["north_viewer_data_agent_verification"] = "pending-ontology-instance-and-agent-retest"
    model["ontology_read_build_group_ids"] = [group["id"] for group in groups]
    save_config(config)
    record("Approved Step 7 Prod SM_Sales Read+Build readback PASS for both sales groups. "
           "Ontology-bound semantic-model queries require Read+Build, unlike the general "
           "direct Data Agent semantic-model Read prerequisite. Workspace Viewer, SSO, "
           "OneLake roles, ontology-only DA_Sales and Dev/Test are unchanged. Real North "
           f"viewer instance and agent checks remain pending. References: {REFERENCES}.")
    print("PERMISSIONS VERIFIED; viewer-session instances and DA_Sales retest still required.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        record(f"Prod ontology reader grant blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
