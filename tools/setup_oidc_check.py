"""Provision only the GitHub test environment and non-secret OIDC check variables."""

import argparse
import json
import sys

from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    gh = cli("gh")
    repository = f"{config['github']['owner']}/{config['github']['repository']}"
    environments = json.loads(run([gh, "api", f"repos/{repository}/environments"]))
    # https://docs.github.com/rest/deployments/environments
    if not any(environment["name"] == "test" for environment in environments["environments"]):
        mutate([gh, "api", "--method", "PUT", f"repos/{repository}/environments/test"],
               args.dry_run)
    variables = json.loads(run([gh, "api", f"repos/{repository}/actions/variables"]))
    existing = {variable["name"]: variable["value"] for variable in variables["variables"]}
    desired = {
        "AZURE_CLIENT_ID": config["entra"]["application"]["client_id"],
        "AZURE_TENANT_ID": config["tenant"]["id"],
        "FABRIC_CAPACITY_ID": config["fabric"]["capacity_id"],
    }
    # https://cli.github.com/manual/gh_variable_set
    for name, value in desired.items():
        if not value:
            raise ContextError(f"OIDC variable {name} is not configured.")
        if name in existing:
            if existing[name] != value:
                raise ContextError(f"STOP: existing GitHub variable {name} differs; no overwrite.")
            continue
        mutate([gh, "variable", "set", name, "--repo", repository, "--body", value],
               args.dry_run)
    if not args.dry_run:
        checked = json.loads(run([gh, "api", f"repos/{repository}/actions/variables"]))
        values = {variable["name"]: variable["value"] for variable in checked["variables"]}
        if any(values.get(name) != value for name, value in desired.items()):
            raise ContextError("GitHub OIDC variable read-back failed.")
        environment = json.loads(run([gh, "api", f"repos/{repository}/environments/test"]))
        config["github"].setdefault("environments", {})["test"] = {
            "id": environment["id"], "name": environment["name"]
        }
        save_config(config)
        record("Verified GitHub test environment and three non-secret OIDC variables; no client secret.")
    print("DRY-RUN: OIDC setup plan complete." if args.dry_run else "OIDC test prerequisites: PASS.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
