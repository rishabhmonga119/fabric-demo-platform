"""Configure owned GitHub deployment controls without changing any Fabric workspace."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = (
    "https://docs.github.com/rest/deployments/environments; "
    "https://docs.github.com/rest/branches/branch-protection; "
    "https://cli.github.com/manual/gh_variable_set"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    github = config["github"]
    gh = cli("gh")
    repository = f"{github['owner']}/{github['repository']}"

    def get(endpoint):
        return json.loads(run([gh, "api", f"repos/{repository}/{endpoint}"]))

    def put(endpoint, body):
        with tempfile.TemporaryDirectory(prefix="fabric-github-controls-") as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(body), encoding="utf-8")
            mutate([gh, "api", "--method", "PUT", f"repos/{repository}/{endpoint}",
                    "--input", str(path)], args.dry_run)

    repo = json.loads(run([gh, "api", f"repos/{repository}"]))
    if repo["id"] != github["repository_id"] or repo["owner"]["id"] != github["owner_id"] or \
            not repo["permissions"]["admin"] or repo["visibility"] != "public":
        raise ContextError("GitHub repository identity/admin access/public visibility differs.")
    test = get("environments/test")
    if test["id"] != github["environments"]["test"]["id"]:
        raise ContextError("The existing Test environment differs; it will not be changed.")
    variables = {item["name"]: item["value"] for item in get("actions/variables?per_page=100")["variables"]}
    expected_variables = {
        "AZURE_CLIENT_ID": config["entra"]["application"]["client_id"],
        "AZURE_TENANT_ID": config["tenant"]["id"],
        "FABRIC_CAPACITY_ID": config["fabric"]["capacity_id"],
    }
    for name, value in expected_variables.items():
        if name in variables and variables[name] != value:
            raise ContextError(f"Existing GitHub variable {name} differs; no overwrite.")
        if name not in variables:
            mutate([gh, "variable", "set", name, "--repo", repository, "--body", value], args.dry_run)
    environments = get("environments?per_page=100")
    if environments["total_count"] > len(environments["environments"]):
        raise ContextError("Environment inventory exceeds one page; no incomplete-policy update.")
    prod = next((item for item in environments["environments"] if item["name"] == "prod"), None)
    prod_body = {
        "wait_timer": 0, "prevent_self_review": False,
        "reviewers": [{"type": "User", "id": github["owner_id"]}],
        "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
    }
    if prod:
        reviewers = [rule for rule in prod["protection_rules"] if rule["type"] == "required_reviewers"]
        if len(reviewers) != 1 or reviewers[0]["prevent_self_review"] or \
                [item["reviewer"]["id"] for item in reviewers[0]["reviewers"]] != [github["owner_id"]] or \
                prod["deployment_branch_policy"] != prod_body["deployment_branch_policy"]:
            raise ContextError("Existing Prod environment controls differ; no unowned-policy overwrite.")
    else:
        put("environments/prod", prod_body)
    branch = get(f"branches/{github['branch']}")
    branch_body = {
        "required_status_checks": {"strict": True, "contexts": ["validate"]},
        "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 1,
                                          "dismiss_stale_reviews": True},
        "restrictions": None, "allow_force_pushes": False, "allow_deletions": False,
    }
    if branch["protected"]:
        protection = get(f"branches/{github['branch']}/protection")
        reviews = protection.get("required_pull_request_reviews", {})
        if protection["enforce_admins"]["enabled"] or reviews.get("required_approving_review_count", 0) < 1 or \
                "validate" not in protection.get("required_status_checks", {}).get("contexts", []):
            raise ContextError("Existing main protection differs; no unowned-policy overwrite.")
    else:
        put(f"branches/{github['branch']}/protection", branch_body)
    if args.dry_run:
        print("DRY-RUN: Prod reviewer/main PR controls and existing OIDC variables checked; Test unchanged.")
        return
    prod = get("environments/prod")
    protection = get(f"branches/{github['branch']}/protection")
    reviewers = [rule for rule in prod["protection_rules"] if rule["type"] == "required_reviewers"]
    checked_variables = {item["name"]: item["value"] for item in get("actions/variables?per_page=100")["variables"]}
    if len(reviewers) != 1 or reviewers[0]["prevent_self_review"] or \
            [item["reviewer"]["id"] for item in reviewers[0]["reviewers"]] != [github["owner_id"]] or \
            prod["deployment_branch_policy"] != prod_body["deployment_branch_policy"] or \
            protection["enforce_admins"]["enabled"] or \
            protection["required_pull_request_reviews"]["required_approving_review_count"] < 1 or \
            "validate" not in protection["required_status_checks"]["contexts"] or \
            any(checked_variables.get(name) != value for name, value in expected_variables.items()):
        raise ContextError("GitHub deployment control readback did not match the approved policy.")
    github["environments"]["prod"] = {"id": prod["id"], "name": prod["name"],
                                      "required_reviewer_id": github["owner_id"]}
    github["metadata_deployment"] = {"workflow": "deploy.yml", "refresh_identity": "demo-admin-user",
                                      "main_pr_required": True, "admin_bypass": True}
    save_config(config)
    record(f"GitHub metadata-only CI controls PASS: Prod environment `{prod['id']}` requires "
           f"owner review; main requires PR/validate with admin bypass. Existing Test environment "
           f"and OIDC variables preserved; no tenant settings or permission grants. References: {REFERENCES}.")
    print("PASS: GitHub Prod approval and main PR controls; no Fabric workspace changed.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, OSError, ValueError) as error:
        record(f"GitHub deployment setup blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
