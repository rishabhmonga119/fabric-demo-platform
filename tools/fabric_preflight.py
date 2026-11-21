"""Read-only Step 2 Fabric capacity, workspace, domain and tenant-setting checks."""

import argparse
import json
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from common import ContextError, cli, load_config, run, verify_context


BASE = "https://api.fabric.microsoft.com"
SKILL = "onelake-catalog-cli"


def fabric_list(endpoint: str, field: str) -> list:
    # Skills for Fabric: fabric-skills/common/COMMON-CORE.md, REST/pagination/auth.
    url = BASE + endpoint
    results = []
    visited = set()
    while url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.fabric.microsoft.com":
            raise ContextError("Refusing to authenticate to an unexpected Fabric pagination origin.")
        if url in visited:
            raise ContextError("Fabric returned a repeated pagination URI.")
        visited.add(url)
        data = json.loads(run([
            cli("az"), "rest", "--method", "get", "--resource", BASE, "--url", url,
            "--headers", f"x-ms-fabric-skill={SKILL}", "--only-show-errors", "--output", "json"
        ]))
        if not isinstance(data.get(field), list):
            raise ContextError(f"Fabric response is missing the expected {field} list: {endpoint}")
        results.extend(data[field])
        if data.get("continuationUri"):
            url = data["continuationUri"]
        elif data.get("continuationToken"):
            initial = urlparse(BASE + endpoint)
            query = dict(parse_qsl(initial.query))
            query["continuationToken"] = data["continuationToken"]
            url = urlunparse(initial._replace(query=urlencode(query)))
        else:
            url = ""
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="This command is always read-only.")
    parser.parse_args()
    verify_context()
    config = load_config()
    # Skill reference: fabric-skills/common/COMMON-CORE.md, Capacity Management.
    capacities = fabric_list("/v1/capacities", "value")
    configured = config["fabric"]["capacity_id"]
    candidates = [
        capacity for capacity in capacities
        if capacity["sku"] == "F4" and capacity["state"] == "Active"
        and (configured is None or capacity["id"] == configured)
    ]
    print("Visible active F4 capacities: " + json.dumps(candidates), flush=True)
    if len(candidates) != 1:
        raise ContextError(
            "Exactly one visible active F4 capacity must match configuration. "
            "Do not create, resize or substitute a capacity."
        )
    # Skill reference: onelake-catalog-cli/references/admin-remediate/domain-crud.md.
    domains = fabric_list("/v1/admin/domains?preview=false", "domains")
    requested_domains = {domain["name"] for domain in config["fabric"]["domains"].values()}
    # Skill reference: onelake-catalog-cli/references/admin-remediate/domain-assign-workspaces.md.
    workspaces = fabric_list("/v1/admin/workspaces?type=Workspace&state=Active", "workspaces")
    requested_workspaces = {stage["workspace_name"] for stage in config["environments"].values()}
    requested_workspaces.add(config["partner"]["workspace_name"])
    # Skill reference: onelake-catalog-cli/references/admin-remediate/trust-curate.md.
    # Current official schema: https://learn.microsoft.com/rest/api/fabric/admin/tenants/list-tenant-settings
    settings = fabric_list("/v1/admin/tenantsettings", "value")
    relevant = re.compile(
        r"service.?principal|git|copilot|openai|cross.?geo|ontology|data.?agent|external.*shar|iq.?shar",
        re.IGNORECASE
    )
    summary = {
        "scope": "Live read-only snapshot; active Workspace type only; all pages exhausted.",
        "capacity": candidates[0],
        "existing_target_domains": [
            domain for domain in domains if domain["displayName"] in requested_domains
        ],
        "existing_target_workspaces": [
            workspace for workspace in workspaces if workspace["name"] in requested_workspaces
        ],
        "relevant_tenant_settings": [
            setting for setting in settings
            if relevant.search(setting["settingName"] + " " + setting.get("title", ""))
        ],
    }
    print(json.dumps(summary, indent=2))
    print("Fabric preflight complete; no resources, settings or configuration changed.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
