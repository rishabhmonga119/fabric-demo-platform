"""Export actual stage and partner OneLake policies without volatile server role IDs."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from bootstrap_fabric_items import MARKER
from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context, write_snapshot
from grant_baseline_readers import baseline_roles
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record

REFERENCES = (
    "e2e-medallion-architecture/SKILL.md; fabric-skills/common/COMMON-CORE.md; "
    "https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/list-data-access-roles"
)


def canonical_roles(roles: list[dict]) -> list[dict]:
    result = [{key: deepcopy(role[key]) for key in ("name", "decisionRules", "members")}
              for role in roles]
    if len({role["name"] for role in result}) != len(result):
        raise ContextError("Duplicate OneLake role names cannot form a safe restore baseline.")
    for role in result:
        for values in role["members"].values():
            if isinstance(values, list):
                values.sort(key=lambda value: json.dumps(value, sort_keys=True))
    return sorted(result, key=lambda role: role["name"])


def capture_roles(config: dict) -> dict:
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    output = {"owner": MARKER, "version": 1, "tenant_id": config["tenant"]["id"], "workspaces": {}}
    for key, stage in [*config["environments"].items(), ("partner", config["partner"])]:
        workspace = stage["workspace_id"]
        verify_stage_capacity(api, config, api.request("GET", f"/v1/workspaces/{workspace}"), stage)
        names = ("LH_PartnerA",) if key == "partner" else ("LH_Landing", "LH_Curated", "MIR_UC_Gold")
        captured = {"workspace_id": workspace, "workspace_name": stage["workspace_name"], "items": {}}
        for name in names:
            item = stage["items"][name]
            roles = api.list(f"/v1/workspaces/{workspace}/items/{item['id']}/dataAccessRoles")
            normalized = canonical_roles(roles)
            if key == "prod" and name == "LH_Curated":
                groups = [config["entra"]["groups"][group] for group in ("sales_north", "sales_south")]
                expected = baseline_roles(roles, workspace, item["id"], groups, config["tenant"]["id"])
                if canonical_roles(expected) != normalized:
                    raise ContextError("Prod is missing the approved baseline sales-reader memberships.")
            captured["items"][name] = {"item_id": item["id"], "roles": normalized}
            print(f"PASS {key}/{name}: {len(roles)} role(s); full policies/members retained.")
        output["workspaces"][key] = captured
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("config") / "onelake_roles.baseline.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Baseline security capture requires the DEMO administrator.")
    verify_context()
    write_snapshot(args.out, capture_roles(load_config()), dry_run=args.dry_run)
    if not args.dry_run:
        record(f"Step 9 actual OneLake role baseline captured at {args.out}: 3 stages and partner; "
               "server role IDs omitted, all policy/member content retained, approved Prod "
               f"sales memberships verified. No access writes. References: {REFERENCES}.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        if "--dry-run" not in sys.argv:
            record(f"OneLake baseline export blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
