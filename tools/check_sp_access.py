"""Read-only GitHub OIDC proof of the configured SP's Fabric Test item access."""

import argparse
import json
import os
import sys
from urllib.request import Request, build_opener

from azure.identity import AzureCliCredential

from common import ContextError, cli, load_config, run, verify_context
from http_api import NoRedirects


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_config()
    workspace_id = config["environments"]["test"]["workspace_id"]
    client_id = config["entra"]["application"]["client_id"]
    if not workspace_id or not client_id:
        raise ContextError("Test workspace and CI/CD client ID must be configured.")
    endpoint = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items"
    if args.dry_run:
        verify_context()
        print(f"DRY-RUN: prove GitHub OIDC SP {client_id} can GET {endpoint}.")
        return
    account = json.loads(run([cli("az"), "account", "show", "--output", "json"]))
    if (
        account["tenantId"] != config["tenant"]["id"]
        or account["user"]["type"] != "servicePrincipal"
        or account["user"]["name"].casefold() != client_id.casefold()
    ):
        raise ContextError("OIDC identity does not match the configured demo tenant/service principal.")
    # Skills for Fabric: fabric-skills/common/COMMON-CORE.md, auth and List Items.
    # Azure login OIDC is already tenant-scoped; do not force --tenant during token acquisition.
    token = AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default")
    headers = {"Authorization": "Bearer " + token.token,
               "x-ms-fabric-skill": "onelake-catalog-cli"}
    with build_opener(NoRedirects()).open(Request(endpoint, headers=headers), timeout=120) as response:
        if response.status != 200:
            raise ContextError(f"SP item access returned HTTP {response.status}.")
        data = json.load(response)
    if not isinstance(data.get("value"), list):
        raise ContextError("SP item access returned an invalid item-list response.")
    summary = f"PASS: configured OIDC service principal can list Test items ({len(data['value'])} on first page)."
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as target:
            target.write(summary + "\n")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
