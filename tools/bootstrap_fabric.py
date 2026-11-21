"""Create Step 2 demo domains/workspaces and verify their scoped permissions."""

import argparse
import json
import sys
import time

from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError
from bootstrap_entra import unique

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


MISSING_PREREQUISITES = (
    "GitHubTenantSettings", "GitIntegrationCrossGeoTenantSwitch",
    "CatalystTenantAdminSwitch", "AllowExternalDataSharingSwitch", "ArtifactIQSharePreview",
)
WRITABLE_SETTING_FIELDS = (
    "enabled", "delegateToCapacity", "delegateToDomain", "delegateToWorkspace",
    "enabledSecurityGroups", "excludedSecurityGroups", "properties",
)


def setting_proposal(current: dict, groups: list[dict]) -> dict:
    if current["canSpecifySecurityGroups"] is not True:
        raise ContextError("Requested tenant setting cannot be restricted to the demo groups.")
    proposed = {key: current[key] for key in WRITABLE_SETTING_FIELDS if key in current}
    proposed["enabled"] = True
    proposed["enabledSecurityGroups"] = groups
    return proposed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    if config["fabric"].get("governance_approved") is not True:
        raise ContextError("Domain governance and tenant-setting scope approval is required.")
    if config["fabric"]["tenant_settings_scope"] != "preserve-enabled":
        raise ContextError("This approved bootstrap preserves existing enabled tenant scopes.")
    if config["fabric"].get("sensitivity_label_skipped") is not True:
        raise ContextError("This bootstrap requires the explicitly approved default-label skip.")
    groups = config["entra"]["groups"]
    application = config["entra"]["application"]
    if any(not group["id"] for group in groups.values()) or not application["service_principal_id"]:
        raise ContextError("Run the Entra bootstrap before creating Fabric objects.")
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="onelake-catalog-cli")
    capacity_id = config["fabric"]["capacity_id"]
    # Skills for Fabric: common/COMMON-CORE.md, Capacity Management.
    capacities = api.list("/v1/capacities")
    if not any(capacity["id"] == capacity_id and capacity["sku"] == "F4"
               and capacity["state"] == "Active" for capacity in capacities):
        raise ContextError("Configured F4 capacity is not visible and Active; never substitute or resize.")
    allowed = [{"graphId": groups[key]["id"], "name": groups[key]["name"]}
               for key in ("admins", "api")]
    # Skill: onelake-catalog-cli/references/admin-remediate/trust-curate.md.
    # https://learn.microsoft.com/rest/api/fabric/admin/tenants/update-tenant-setting
    settings = api.list("/v1/admin/tenantsettings")
    for name in MISSING_PREREQUISITES:
        current = unique(settings, "settingName", name)
        if current is None:
            raise ContextError(f"Required setting not exposed: {name}; no replacement name invented.")
        if current["enabled"] is True:
            print(f"Preserve existing enabled setting and scope: {name}", flush=True)
            continue
        proposed = setting_proposal(current, allowed)
        print(f"{name} current -> proposed: " + json.dumps({"current": current, "proposed": proposed}))
        api.request("POST", f"/v1/admin/tenantsettings/{name}/update", proposed,
                    dry_run=args.dry_run)
        if not args.dry_run:
            checked = unique(api.list("/v1/admin/tenantsettings"), "settingName", name)
            if checked is None or checked["enabled"] is not True:
                raise ApiError(f"Tenant setting {name} enablement read-back failed.")
            if {group["graphId"] for group in checked["enabledSecurityGroups"]} != {
                group["graphId"] for group in allowed
            }:
                raise ApiError(f"Tenant setting {name} scope read-back failed.")
            record(f"Verified tenant setting `{name}` enabled for only the two demo admin/API groups; existing enabled scopes preserved.")

    domains = api.list("/v1/admin/domains?preview=false", "domains")
    for domain_config in config["fabric"]["domains"].values():
        if len(domain_config["description"]) > 256:
            raise ContextError("Approved domain description exceeds the documented 256-character limit.")
        domain = unique(domains, "displayName", domain_config["name"])
        if domain:
            if domain_config["id"] != domain["id"]:
                raise ContextError(f"STOP: existing domain {domain_config['name']} is not recorded as ours.")
        else:
            # Skill: onelake-catalog-cli/references/admin-remediate/domain-crud.md.
            domain = api.request("POST", "/v1/admin/domains?preview=false", {
                "displayName": domain_config["name"], "description": domain_config["description"]
            }, dry_run=args.dry_run)
        if domain is None:
            print(f"DRY-RUN: assign approved group ownership/contributors to new {domain_config['name']}; default label explicitly skipped.")
            continue
        domain_id = domain["id"]
        if not args.dry_run:
            domain_config["id"] = domain_id
            save_config(config)
        # Skill: onelake-catalog-cli/references/admin-remediate/domain-roles.md.
        roles = api.list(f"/v1/admin/domains/{domain_id}/roleAssignments")
        for role, request_type, group_field in (
            ("Admin", "Admins", "administrator_group"),
            ("Contributor", "Contributors", "contributor_group"),
        ):
            selected = next(group for group in groups.values()
                            if group["name"] == domain_config[group_field])
            if not any(assignment["role"] == role and assignment["principal"].get("id") == selected["id"]
                       for assignment in roles):
                api.request("POST", f"/v1/admin/domains/{domain_id}/roleAssignments/bulkAssign",
                            {"type": request_type, "principals": [{"id": selected["id"], "type": "Group"}]},
                            dry_run=args.dry_run)
        if not args.dry_run:
            roles = api.list(f"/v1/admin/domains/{domain_id}/roleAssignments")
            for assignment in roles:
                if assignment["role"] == "Contributor" and assignment["principal"]["type"] == "EntireTenant":
                    principal = assignment["principal"]
                    api.request("POST", f"/v1/admin/domains/{domain_id}/roleAssignments/bulkUnassign",
                                {"type": "Contributors",
                                 "principals": [{key: principal[key] for key in ("id", "type")}]})
            roles = api.list(f"/v1/admin/domains/{domain_id}/roleAssignments")
            for role_name, group_field in (("Admin", "administrator_group"),
                                           ("Contributor", "contributor_group")):
                selected = next(group for group in groups.values()
                                if group["name"] == domain_config[group_field])
                if not any(role["role"] == role_name and role["principal"].get("id") == selected["id"]
                           and role["principal"]["type"] == "Group" for role in roles):
                    raise ApiError(f"Domain {role_name} group read-back failed.")
            if any(role["principal"]["type"] == "EntireTenant" for role in roles):
                raise ApiError("Domain contributor scope still contains EntireTenant.")
            record(f"Verified domain `{domain_config['name']}`: `{domain_id}`; approved group owner/contributors; default label explicitly skipped.")

    workspaces = api.list("/v1/admin/workspaces?type=Workspace&state=Active", "workspaces")
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    for stage, workspace_config in (*config["environments"].items(), ("partner", config["partner"])):
        domain_id = config["fabric"]["domains"]["partners" if stage == "partner" else "analytics"]["id"]
        existing = unique(workspaces, "name", workspace_config["workspace_name"])
        if existing:
            if workspace_config["workspace_id"] != existing["id"]:
                raise ContextError(f"STOP: existing workspace {workspace_config['workspace_name']} is not recorded as ours.")
            workspace_id = existing["id"]
        elif args.dry_run:
            print(f"DRY-RUN: create {workspace_config['workspace_name']} on existing F4 with its new domain, then assign approved roles.")
            continue
        else:
            # Skill: fabric-skills/common/COMMON-CORE.md, Create Workspace.
            workspace = api.request("POST", "/v1/workspaces", {
                "displayName": workspace_config["workspace_name"],
                "description": f"Demo workspace owned by {owner}",
                "capacityId": capacity_id, "domainId": domain_id,
            })
            if workspace is None:
                raise ApiError("Create Workspace did not return its resource ID.")
            workspace_id = workspace["id"]
            workspace_config["workspace_id"] = workspace_id
            save_config(config)
        if not args.dry_run:
            deadline = time.monotonic() + 300
            while True:
                info = api.request("GET", f"/v1/workspaces/{workspace_id}")
                if info is None or info.get("capacityId") != capacity_id or info.get("domainId") != domain_id:
                    raise ApiError("Workspace F4/domain read-back differs; no reassignment attempted.")
                if info["capacityAssignmentProgress"] == "Completed":
                    break
                if info["capacityAssignmentProgress"] == "Failed" or time.monotonic() >= deadline:
                    raise ApiError("Workspace capacity assignment did not complete.")
                time.sleep(5)
        assignments = api.list(f"/v1/workspaces/{workspace_id}/roleAssignments")
        desired = [(groups["admins"]["id"], "Group", "Admin")]
        if stage in ("dev", "test", "prod"):
            desired.append((application["service_principal_id"], "ServicePrincipal",
                            "Contributor" if stage == "dev" else "Admin"))
        if stage == "prod":
            desired.extend((groups[key]["id"], "Group", "Viewer") for key in ("sales_north", "sales_south"))
        # Skill: fabric-skills/common/COMMON-CORE.md, Workspace Role Assignment.
        for principal_id, principal_type, role in desired:
            matches = [assignment for assignment in assignments
                       if assignment["principal"].get("id") == principal_id]
            if matches:
                if any(assignment["role"] != role for assignment in matches):
                    raise ContextError("STOP: existing workspace role differs; no overwrite attempted.")
                continue
            api.request("POST", f"/v1/workspaces/{workspace_id}/roleAssignments",
                        {"principal": {"id": principal_id, "type": principal_type}, "role": role},
                        dry_run=args.dry_run)
        if not args.dry_run:
            checked = api.list(f"/v1/workspaces/{workspace_id}/roleAssignments")
            if not all(any(item["principal"].get("id") == principal_id and item["role"] == role
                           for item in checked) for principal_id, _, role in desired):
                raise ApiError("Workspace role read-back failed.")
            record(f"Verified workspace `{workspace_config['workspace_name']}`: `{workspace_id}`; F4, domain and exact required roles PASS.")
    print("DRY-RUN: Fabric plan complete; no resources/settings changed." if args.dry_run
          else "Fabric bootstrap checks: PASS (four workspaces on existing F4; domains and roles verified).")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Fabric bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
