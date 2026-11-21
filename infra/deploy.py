"""Deploy only Step 1 resources after context, ownership and cost checks."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ContextError, ROOT, cli, load_config, mutate, run, verify_context


def record(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with (ROOT / "docs" / "BUILD_LOG.md").open("a", encoding="utf-8") as target:
        target.write(f"\n- {stamp}: {message}\n")


def owned(resource: dict, owner: str) -> bool:
    tags = resource.get("tags") or {}
    return tags.get("demoOwner") == owner and tags.get("createdBy") == "copilot-demo-build"


def save_config(config: dict) -> None:
    with (ROOT / "config" / "environments.yml").open("w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, sort_keys=False)


def ensure_storage_network(config: dict, dry_run: bool = False) -> None:
    azure = config["azure"]
    if not azure["storage_account_name"]:
        raise ContextError("Storage account has not been deployed yet.")
    az = cli("az")
    command = [
        az, "storage", "account", "show", "--resource-group", azure["resource_group"],
        "--name", azure["storage_account_name"], "--only-show-errors", "--output", "json"
    ]
    storage = json.loads(run(command))
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    if not owned(storage, owner):
        raise ContextError("STOP: cannot change network settings on unowned storage.")
    if storage["publicNetworkAccess"] != "Enabled":
        update = [
            az, "storage", "account", "update", "--resource-group", azure["resource_group"],
            "--name", azure["storage_account_name"], "--public-network-access", "Enabled",
            "--only-show-errors", "--output", "json"
        ]
        # Official CLI help: az storage account update --help, --public-network-access.
        mutate(update, dry_run)
        if dry_run:
            return
        storage = json.loads(run(command))
        record("Re-applied the demo-only public network setting with `az storage account update`.")
    if storage["publicNetworkAccess"] != "Enabled" or storage["allowBlobPublicAccess"] is not False:
        raise RuntimeError(
            "Storage network verification failed: expected publicNetworkAccess=Enabled "
            f"and allowBlobPublicAccess=False; got {storage['publicNetworkAccess']} "
            f"and {storage['allowBlobPublicAccess']}."
        )
    print("Storage network verification: PASS")
    if not dry_run:
        record("Storage network verification: PASS (public endpoint enabled; anonymous blobs disabled).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--region", help="Override the configured deployment region.")
    parser.add_argument("--repair-network-only", action="store_true",
                        help="Verify/reapply the demo storage network setting without redeploying.")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    azure = config["azure"]
    if args.region:
        azure["region"] = args.region
    group = azure["resource_group"]
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    az = cli("az")

    def read(*arguments: str):
        return json.loads(run([az, *arguments, "--only-show-errors", "--output", "json"]))

    exists = read("group", "exists", "--name", group)
    if exists:
        current_group = read("group", "show", "--name", group)
        if not owned(current_group, owner):
            raise ContextError(f"STOP: existing resource group {group} was not created by us.")
        resources = read("resource", "list", "--resource-group", group)
        for resource in resources:
            if resource["type"].casefold() in (
                "microsoft.storage/storageaccounts",
                "microsoft.databricks/workspaces",
                "microsoft.databricks/accessconnectors",
            ) and not owned(resource, owner):
                raise ContextError(f"STOP: would overwrite an unowned resource: {resource['id']}")

    workspaces = read("resource", "list", "--resource-type", "Microsoft.Databricks/workspaces")
    if workspaces and (
        len(workspaces) != 1
        or workspaces[0]["name"] != azure["databricks_workspace_name"]
        or not owned(workspaces[0], owner)
    ):
        raise ContextError("STOP: one-workspace cost guardrail conflicts with existing resources.")
    managed_group = "rg-demo-databricks-managed"
    if not exists and read("group", "exists", "--name", managed_group):
        raise ContextError(f"STOP: managed resource group {managed_group} already exists.")
    if args.repair_network_only:
        ensure_storage_network(config, args.dry_run)
        return
    parameters = [
        f"location={azure['region']}",
        f"workspaceName={azure['databricks_workspace_name']}",
        f"owner={owner}",
    ]
    if azure["storage_account_name"]:
        parameters.append(f"storageAccountName={azure['storage_account_name']}")
    template = str(ROOT / "infra" / "databricks.bicep")
    group_command = [
        az, "group", "create", "--name", group, "--location", azure["region"],
        "--tags", f"demoOwner={owner}", "createdBy=copilot-demo-build",
        "--only-show-errors", "--output", "json"
    ]
    deployment = [
        az, "deployment", "group", "create", "--resource-group", group,
        "--name", "demo-step-1", "--template-file", template, "--parameters",
        *parameters, "--mode", "Incremental", "--no-wait",
        "--only-show-errors", "--output", "json"
    ]
    if args.dry_run:
        print(f"DRY-RUN: ensure Microsoft.Databricks and Microsoft.Storage are registered.")
        if not exists:
            mutate(group_command, dry_run=True)
        mutate(deployment, dry_run=True)
        print("DRY-RUN: no resources, configuration or logs changed.")
        return

    for namespace in ("Microsoft.Databricks", "Microsoft.Storage"):
        provider = read("provider", "show", "--namespace", namespace)
        if provider["registrationState"] != "Registered":
            if provider["registrationState"] != "Registering":
                mutate([az, "provider", "register", "--namespace", namespace,
                        "--only-show-errors", "--output", "json"])
                record(f"Requested registration of `{namespace}` for Step 1.")
            registration_deadline = time.monotonic() + 600
            while time.monotonic() < registration_deadline:
                provider = read("provider", "show", "--namespace", namespace)
                if provider["registrationState"] == "Registered":
                    break
                time.sleep(10)
            else:
                raise TimeoutError(f"{namespace} registration did not finish within 10 minutes.")
        record(f"Provider `{namespace}` registration: PASS.")

    if not exists:
        current_group = json.loads(mutate(group_command))
        azure["resource_group_id"] = current_group["id"]
        record(f"Created resource group `{group}`: `{current_group['id']}`.")
        save_config(config)
    # https://learn.microsoft.com/cli/azure/deployment/group
    validation = [
        az, "deployment", "group", "validate", "--resource-group", group,
        "--template-file", template, "--parameters", *parameters,
        "--only-show-errors", "--output", "json"
    ]
    verify_context()
    record(f"Validating Step 1 resources in `{azure['region']}` using `az deployment group validate`.")
    run(validation)
    record("ARM provider validation: PASS for `infra/databricks.bicep`.")
    mutate(deployment)
    record("Submitted `az deployment group create --name demo-step-1 --mode Incremental --no-wait`.")
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        state = read("deployment", "group", "show", "--resource-group", group,
                     "--name", "demo-step-1")
        status = state["properties"]["provisioningState"]
        print(f"Step 1 ARM deployment: {status}", flush=True)
        if status == "Succeeded":
            outputs = state["properties"]["outputs"]
            keys = {
                "workspaceId": "databricks_workspace_id",
                "workspaceUrl": "databricks_workspace_url",
                "storageAccountName": "storage_account_name",
                "storageAccountId": "storage_account_id",
                "accessConnectorId": "access_connector_id",
                "accessConnectorPrincipalId": "access_connector_principal_id",
                "managedResourceGroupId": "managed_resource_group_id",
            }
            for output, key in keys.items():
                azure[key] = outputs[output]["value"]
                record(f"`{key}` = `{azure[key]}`.")
            save_config(config)
            ensure_storage_network(config)
            record("Azure deployment: PASS. Unity Catalog configuration/checks still pending.")
            return
        if status in ("Failed", "Canceled"):
            for resource in read("resource", "list", "--resource-group", group):
                if not owned(resource, owner):
                    continue
                resource_type = resource["type"].casefold()
                if resource_type == "microsoft.storage/storageaccounts":
                    azure["storage_account_name"] = resource["name"]
                    azure["storage_account_id"] = resource["id"]
                elif resource_type == "microsoft.databricks/accessconnectors":
                    azure["access_connector_id"] = resource["id"]
                elif resource_type == "microsoft.databricks/workspaces":
                    azure["databricks_workspace_id"] = resource["id"]
                record(f"Partial deployment resource: `{resource['name']}` = `{resource['id']}`.")
            save_config(config)
            failure = json.dumps(state["properties"].get("error"), ensure_ascii=True)
            record(f"Azure deployment FAILED: `{failure}`.")
            raise RuntimeError(f"Step 1 deployment failed: {failure}")
        time.sleep(15)
    raise TimeoutError("Step 1 deployment did not finish within 30 minutes.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"Step 1 blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
