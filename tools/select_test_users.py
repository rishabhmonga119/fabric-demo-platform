"""Reuse explicitly selected licensed accounts without changing licences/passwords."""

import argparse
import sys
from urllib.parse import quote

from bootstrap_entra import has_membership
from check_demo_licenses import license_features
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def assert_viewer_eligible(user_id: str, assignments: list, member_groups: set[str]) -> None:
    for assignment in assignments:
        if assignment["role"] not in ("Admin", "Member", "Contributor"):
            continue
        principal = assignment["principal"]
        applies = (
            principal["type"] == "EntireTenant"
            or (principal["type"] == "User" and principal["id"] == user_id)
            or (principal["type"] == "Group" and principal["id"] in member_groups)
        )
        if applies:
            raise ContextError("Selected account has a privileged Prod role that bypasses OneLake security.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--north", required=True)
    parser.add_argument("--south", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.north.casefold() == args.south.casefold():
        parser.error("Use different accounts for North and South.")
    verify_context()
    config = load_config()
    graph = Api("https://graph.microsoft.com", config["tenant"]["id"])
    fabric = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
                 skill="onelake-catalog-cli")
    workspace_id = config["environments"]["prod"]["workspace_id"]
    if not workspace_id:
        raise ContextError("Prod workspace must exist before selecting viewer accounts.")
    # Skill reference: fabric-skills/common/COMMON-CORE.md, Workspace Role Assignment.
    assignments = fabric.list(f"/v1/workspaces/{workspace_id}/roleAssignments")
    privileged_groups = {
        item["principal"]["id"] for item in assignments
        if item["role"] in ("Admin", "Member", "Contributor") and item["principal"]["type"] == "Group"
    }
    if privileged_groups - {group["id"] for group in config["entra"]["groups"].values()}:
        raise ContextError("Prod has an unmanaged privileged group; review effective access before reuse.")
    selected = {}
    for region, upn in (("north", args.north), ("south", args.south)):
        if not upn.casefold().endswith("@" + config["tenant"]["domain"].casefold()):
            raise ContextError("Selected test account must belong to the verified demo tenant.")
        user = graph.request(
            "GET", f"/v1.0/users/{quote(upn)}?$select=id,userPrincipalName,accountEnabled"
        )
        if user is None or user["accountEnabled"] is not True:
            raise ContextError(f"Selected account is missing or disabled: {upn}")
        licences = graph.list(f"/v1.0/users/{user['id']}/licenseDetails")
        enabled = {plan["servicePlanName"] for licence in licences for plan in licence["servicePlans"]
                   if plan["provisioningStatus"] == "Success"}
        if not all(license_features(enabled).values()):
            raise ContextError(f"Selected account lacks active Power BI Pro/M365 Copilot capabilities: {upn}")
        membership = {
            group_id for group_id in privileged_groups
            if has_membership(graph, group_id, user["id"])
        }
        assert_viewer_eligible(user["id"], assignments, membership)
        opposite = "south" if region == "north" else "north"
        if has_membership(graph, config["entra"]["groups"][f"sales_{opposite}"]["id"], user["id"]):
            raise ContextError("Selected account is already in the opposite sales group; no removal attempted.")
        selected[region] = {"id": user["id"], "upn": user["userPrincipalName"], "reuse_existing": True}
        print(f"Verified licensed, non-privileged {region} viewer: {user['userPrincipalName']}", flush=True)

    for region, user in selected.items():
        group = config["entra"]["groups"][f"sales_{region}"]
        if not has_membership(graph, group["id"], user["id"]):
            # https://learn.microsoft.com/graph/api/group-post-members
            graph.request("POST", f"/v1.0/groups/{group['id']}/members/$ref",
                          {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user['id']}"},
                          dry_run=args.dry_run)
        if not args.dry_run and not has_membership(graph, group["id"], user["id"]):
            raise ApiError("Selected test-user membership read-back failed.")
    if args.dry_run:
        print("DRY-RUN: selected-user plan complete; no licences, passwords, users or config changed.")
        return
    if "created_test_users" not in config["entra"]:
        config["entra"]["created_test_users"] = config["entra"]["users"]
    config["entra"]["users"] = selected
    save_config(config)
    for region, user in selected.items():
        record(f"Selected existing licensed `{region}` viewer `{user['upn']}`: `{user['id']}`; licences/password unchanged.")
    print("Test viewer selection: PASS; existing licensed accounts reused without licence transfers.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Test-user selection blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
