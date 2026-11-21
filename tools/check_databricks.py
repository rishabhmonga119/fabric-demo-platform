"""Read-only Databricks identity, metastore and compute preflight."""

import argparse
import json
import os
import sys
import time

from common import ContextError, cli, load_config, run, verify_context


def workspace_environment(config: dict) -> dict[str, str]:
    azure = config["azure"]
    if not azure["databricks_workspace_url"] or not azure["databricks_workspace_id"]:
        raise ContextError("Step 1 Azure deployment outputs are not yet available.")
    environment = os.environ.copy()
    environment["DATABRICKS_HOST"] = azure["databricks_workspace_url"]
    environment["DATABRICKS_AZURE_RESOURCE_ID"] = azure["databricks_workspace_id"]
    environment["DATABRICKS_AUTH_TYPE"] = "azure-cli"
    # https://learn.microsoft.com/azure/databricks/dev-tools/auth/env-vars
    environment["ARM_TENANT_ID"] = config["tenant"]["id"]
    environment["ARM_ENVIRONMENT"] = "PUBLIC"
    return environment


def inspect(config: dict, wait_ready: int = 0) -> dict:
    environment = workspace_environment(config)
    executable = cli("databricks")

    def read(*arguments: str):
        return json.loads(run([executable, *arguments, "--output", "json"], env=environment))

    deadline = time.monotonic() + wait_ready
    while True:
        try:
            identity = read("current-user", "me")
            break
        except ContextError as error:
            if (
                "Did not find workspace with specified org ID" not in str(error)
                or time.monotonic() >= deadline
            ):
                raise
            print("New workspace is not yet available in Databricks; waiting 30 seconds.",
                  flush=True)
            time.sleep(30)
    if identity.get("userName", "").casefold() != config["tenant"]["admin_upn"].casefold():
        raise ContextError("Databricks identity differs from the required demo administrator.")
    print(f"Databricks identity: PASS ({identity['userName']})")
    assignment = read("metastores", "current")
    print(f"Unity Catalog assignment: {json.dumps(assignment)}")
    metastore = read("metastores", "get", assignment["metastore_id"])
    print("Metastore: " + json.dumps({
        key: metastore.get(key) for key in
        ("metastore_id", "name", "region", "owner", "created_at", "created_by",
         "external_access_enabled")
    }))
    warehouses = read("warehouses", "list")
    print("Existing SQL warehouses: " + json.dumps([
        {key: warehouse.get(key) for key in
         ("id", "name", "state", "auto_stop_mins", "enable_serverless_compute")}
        for warehouse in warehouses
    ]))
    return metastore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Checks are always read-only.")
    parser.add_argument("--wait-ready", type=int, default=0,
                        help="Seconds to wait for a newly deployed workspace (maximum 600).")
    parser.add_argument("--rest", action="store_true",
                        help="Diagnose current-user access with Azure CLI REST instead of the SDK.")
    args = parser.parse_args()
    if not 0 <= args.wait_ready <= 600:
        parser.error("--wait-ready must be between 0 and 600 seconds.")
    verify_context()
    config = load_config()
    if args.rest:
        workspace_environment(config)
        # https://docs.databricks.com/api/scim/v1/me
        # https://learn.microsoft.com/azure/databricks/dev-tools/auth/aad-token-manual
        endpoint = (config["azure"]["databricks_workspace_url"]
                    + "/api/2.0/preview/scim/v2/Me")
        identity = json.loads(run([
            cli("az"), "rest", "--method", "get", "--url", endpoint,
            "--resource", "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d",
            "--only-show-errors", "--output", "json"
        ]))
        if identity.get("userName", "").casefold() != config["tenant"]["admin_upn"].casefold():
            raise ContextError("REST Databricks identity differs from the required demo administrator.")
        print(f"REST Databricks identity: PASS ({identity['userName']})")
    else:
        inspect(config, args.wait_ready)


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
