"""Add the two approved sales groups to the Prod Curated DefaultReader role only."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import sys

from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCE = "https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/create-or-update-data-access-roles"


def baseline_roles(roles: list[dict], workspace: str, item: str, groups: list[dict],
                   tenant: str) -> list[dict]:
    if len(roles) != 1 or roles[0]["name"] != "DefaultReader":
        raise ContextError("Prod no longer has the approved DefaultReader-only baseline; no overwrite.")
    source = roles[0]
    rules = source["decisionRules"]
    expected_permissions = {"Action": ["Read"], "Path": ["*"]}
    if len(rules) != 1 or rules[0].get("effect") != "Permit" or rules[0].get("constraints") or \
            {entry["attributeName"]: entry["attributeValueIncludedIn"]
             for entry in rules[0]["permission"]} != expected_permissions:
        raise ContextError("DefaultReader policy differs from the approved unrestricted read baseline.")
    members = source.get("members", {})
    if members.get("fabricItemMembers") != [
            {"sourcePath": f"{workspace}/{item}", "itemAccess": ["ReadAll"]}]:
        raise ContextError("DefaultReader virtual membership differs; no policy overwrite.")
    result = {key: deepcopy(source[key]) for key in ("name", "decisionRules", "members")}
    explicit = result["members"].setdefault("microsoftEntraMembers", [])
    for group in groups:
        wanted = {"tenantId": tenant, "objectId": group["id"]}
        if wanted not in explicit:
            explicit.append(wanted)
    return [result]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-prod-baseline-read", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Metadata CI cannot grant OneLake access.")
    verify_context()
    if not args.dry_run and not args.approved_prod_baseline_read:
        raise ContextError("Explicit approval of the two Prod baseline data-reader memberships is required.")
    config = load_config()
    stage = config["environments"]["prod"]
    workspace = stage["workspace_id"]
    item = stage["items"]["LH_Curated"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    verify_stage_capacity(api, config, api.request("GET", f"/v1/workspaces/{workspace}"), stage)
    actual = [value for value in api.list(f"/v1/workspaces/{workspace}/items?type=Lakehouse")
              if value["displayName"] == "LH_Curated"]
    if len(actual) != 1 or actual[0]["id"] != item["id"]:
        raise ContextError("The Prod Curated lakehouse differs from the approved target.")
    endpoint = f"/v1/workspaces/{workspace}/items/{item['id']}/dataAccessRoles"
    response = api.request("GET", endpoint, with_response_info=True)
    if response["body"].get("continuationToken") or response["body"].get("continuationUri"):
        raise ContextError("Unexpected multi-page role set; no incomplete role replacement.")
    roles = response["body"]["value"]
    groups = [config["entra"]["groups"][key] for key in ("sales_north", "sales_south")]
    desired = baseline_roles(roles, workspace, item["id"], groups, config["tenant"]["id"])
    current = [{key: value[key] for key in ("name", "decisionRules", "members")} for value in roles]
    if desired != current:
        etag = response.get("etag")
        if not isinstance(etag, str) or not etag.startswith('"') or not etag.endswith('"'):
            raise ContextError("The role collection has no quoted concurrency ETag; no unsafe write.")
        api.request("PUT", endpoint, {"value": desired}, dry_run=args.dry_run, if_match=etag)
    if args.dry_run:
        print("DRY-RUN: only the two sales groups join Prod Curated DefaultReader; policy and other memberships preserved.")
        return
    persisted = api.list(endpoint)
    observed = [{key: value[key] for key in ("name", "decisionRules", "members")} for value in persisted]
    if observed != desired:
        raise ApiError("The approved OneLake role memberships did not persist exactly.")
    checkpoint = config.setdefault("copilot", {}).setdefault("step7", {})
    checkpoint.update({
        "viewer_source_access_grant": "verified-prod-default-reader",
        "viewer_source_access_granted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "north_viewer_answer_verification": "pending-viewer-retest",
    })
    item.setdefault("onelake_security", {})["baseline_sales_group_ids"] = [g["id"] for g in groups]
    save_config(config)
    record(f"Approved Step 7 Prod LH_Curated DefaultReader membership grant/readback PASS: "
           f"{', '.join(group['name'] for group in groups)}. Existing virtual ReadAll "
           "membership and unrestricted Read policy preserved; no Build/Contributor, "
           "SSO/connection, mirror, tenant or Dev/Test change. Viewer-session retest is "
           f"still required. Skill: e2e-medallion-architecture/common references; {REFERENCE}.")
    print("PASS: approved Prod-only baseline data role membership; retry the North viewer session.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        record(f"Prod baseline data-reader grant blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
