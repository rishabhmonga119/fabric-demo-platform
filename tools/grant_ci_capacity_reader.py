"""Grant explicitly approved Reader access only on the existing demo F4 capacity."""

import argparse
import json
import sys
from uuid import NAMESPACE_URL, uuid5

from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context
from http_api import Api

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

SCOPE = "/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/fabric-demo-rg/providers/Microsoft.Fabric/capacities/capacityswitzerlandnorth"
READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
PRINCIPAL = "e4234475-0f90-44c2-b256-20ce1b6c7614"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-capacity-reader", action="store_true")
    args = parser.parse_args()
    verify_context()
    if not args.dry_run and not args.approved_capacity_reader:
        raise ContextError("The new capacity-only Reader grant requires explicit approval.")
    config = load_config()
    if config["entra"]["application"]["service_principal_id"] != PRINCIPAL:
        raise ContextError("The configured principal differs from the explicitly approved grant.")
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if len(capacities) != 1 or capacities[0].get("azureResourceId", "").casefold() != SCOPE.casefold() or \
            capacities[0]["sku"] != "F4" or capacities[0]["state"] != "Active":
        raise ContextError("The capacity differs from the exact approved existing Active F4.")
    az = cli("az")

    def assignments():
        rows = json.loads(run([az, "role", "assignment", "list", "--assignee-object-id", PRINCIPAL,
                               "--scope", SCOPE, "--fill-principal-name", "false",
                               "--output", "json"]))
        return [item for item in rows if item["scope"].casefold() == SCOPE.casefold()
                and item["roleDefinitionId"].split("/")[-1] == READER]

    existing = assignments()
    if len(existing) > 1:
        raise ContextError("Multiple Reader assignments exist; no duplicate or deletion.")
    if not existing:
        name = str(uuid5(NAMESPACE_URL, f"fabric-demo-platform/capacity-reader/{SCOPE}/{PRINCIPAL}"))
        mutate([az, "role", "assignment", "create", "--assignee-object-id", PRINCIPAL,
                "--assignee-principal-type", "ServicePrincipal", "--role", READER,
                "--scope", SCOPE, "--name", name, "--output", "json"], args.dry_run)
    if args.dry_run:
        print("DRY-RUN: Reader on the single F4 resource only; no subscription or administration grant.")
        return
    existing = assignments()
    if len(existing) != 1:
        raise ContextError("Capacity Reader grant did not persist.")
    config["fabric"]["capacity_resource_id"] = SCOPE
    config["github"]["capacity_reader"] = {
        "principal_id": PRINCIPAL, "scope": SCOPE, "role_assignment_id": existing[0]["id"],
    }
    save_config(config)
    record(f"Explicitly approved capacity-only Azure Reader grant PASS: `{existing[0]['id']}` "
           f"for `{PRINCIPAL}` at `{SCOPE}`. No Contributor/Admin, subscription role, resize "
           "or resource creation. References: fabric-skills/common/COMMON-CORE.md; "
           "https://learn.microsoft.com/cli/azure/role/assignment#az-role-assignment-create.")
    print("PASS: approved Reader access on the single existing F4 capacity.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, OSError, ValueError) as error:
        record(f"Capacity Reader grant blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
