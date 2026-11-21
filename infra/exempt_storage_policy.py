"""Create the approved public-network rule exemption on existing storage accounts."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infra.deploy import record, save_config
from tools.common import ContextError, cli, load_config, mutate, run, verify_context


def verify_exemption(exemption: dict, account_id: str, rule: dict, owner: str) -> None:
    expected_id = f"{account_id}/providers/Microsoft.Authorization/policyExemptions/{rule['name']}"
    metadata = exemption.get("metadata") or {}
    if (
        exemption["id"].casefold() != expected_id.casefold()
        or exemption["policyAssignmentId"].casefold() != rule["assignment_id"].casefold()
        or exemption["policyDefinitionReferenceIds"] != [rule["definition_reference_id"]]
        or exemption["exemptionCategory"] != "Waiver"
        or metadata.get("demoOwner") != owner
        or metadata.get("createdBy") != "copilot-demo-build"
    ):
        raise ContextError(f"STOP: exemption is unowned or broader than approved: {expected_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    rule = config["azure"]["storage_policy_exemption"]
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    az = cli("az")

    def read(*arguments: str):
        return json.loads(run([az, *arguments, "--only-show-errors", "--output", "json"]))

    inventory = read("storage", "account", "list")
    accounts = {account["id"].casefold(): account for account in inventory}
    targets = rule["target_resource_ids"]
    if not targets:
        targets = [account["id"] for account in inventory]
        if not targets:
            raise ContextError("No existing storage accounts found; no exemption will be created.")
        if not args.dry_run:
            rule["target_resource_ids"] = targets
            save_config(config)
            record(f"Approved existing-account exemption snapshot: {len(targets)} accounts; no future accounts.")
    prefix = f"/subscriptions/{config['azure']['subscription_id']}/resourcegroups/"
    for account_id in targets:
        if (
            not account_id.casefold().startswith(prefix.casefold())
            or "/providers/microsoft.storage/storageaccounts/" not in account_id.casefold()
            or account_id.casefold() not in accounts
        ):
            raise ContextError(f"Exemption target is missing or outside the approved subscription: {account_id}")

    existing_exemptions = read(
        "policy", "exemption", "list",
        "--scope", f"/subscriptions/{config['azure']['subscription_id']}",
        "--disable-scope-strict-match", "true"
    )
    for account_id in targets:
        if account_id in rule.get("excluded_accounts", {}):
            print(f"Approved protected-account exclusion: {account_id}", flush=True)
            continue
        expected_id = f"{account_id}/providers/Microsoft.Authorization/policyExemptions/{rule['name']}"
        existing = [
            exemption for exemption in existing_exemptions
            if exemption["id"].casefold() == expected_id.casefold()
        ]
        if len(existing) > 1:
            raise ContextError(f"Multiple exemption records found: {expected_id}")
        if existing:
            verify_exemption(existing[0], account_id, rule, owner)
            print(f"Existing approved exemption: PASS ({account_id})", flush=True)
            if not args.dry_run:
                rule["created_exemptions"][account_id] = existing[0]["id"]
                save_config(config)
            continue
        command = [
            az, "policy", "exemption", "create", "--name", rule["name"],
            "--scope", account_id, "--policy-assignment", rule["assignment_id"],
            "--exemption-category", "Waiver", "--display-name", "Demo storage public-network exception",
            "--description", "Approved existing-storage-account waiver for public network access only.",
            "--only-show-errors", "--output", "json"
        ]
        metadata = {"demoOwner": owner, "createdBy": "copilot-demo-build"}
        references = [rule["definition_reference_id"]]
        # https://learn.microsoft.com/cli/azure/policy/exemption
        # https://learn.microsoft.com/azure/governance/policy/concepts/exemption-structure
        if args.dry_run:
            mutate([*command, "--policy-definition-reference-ids",
                    json.dumps(references), "--metadata", json.dumps(metadata)], dry_run=True)
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="demo-exemption-") as directory:
                metadata_file = Path(directory) / "metadata.json"
                references_file = Path(directory) / "references.json"
                metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
                references_file.write_text(json.dumps(references), encoding="utf-8")
                mutate([*command, "--policy-definition-reference-ids", f"@{references_file}",
                        "--metadata", f"@{metadata_file}"])
        except ContextError as error:
            if (
                rule.get("exclude_platform_denied") is True
                and "DenyAssignmentAuthorizationFailed" in str(error)
            ):
                rule["excluded_accounts"][account_id] = "DenyAssignmentAuthorizationFailed"
                save_config(config)
                record(f"Explicitly approved protected-account exclusion: `{account_id}` (platform deny assignment).")
                print(f"EXCLUDED with user approval: {account_id}", flush=True)
                continue
            raise
        exemption = read("policy", "exemption", "show", "--name", rule["name"], "--scope", account_id)
        verify_exemption(exemption, account_id, rule, owner)
        rule["created_exemptions"][account_id] = exemption["id"]
        save_config(config)
        record(f"Verified exemption `{exemption['id']}` for only `{rule['definition_reference_id']}`.")
        print(f"Created approved exemption: PASS ({account_id})", flush=True)
    if args.dry_run:
        print(f"DRY-RUN: plan complete for {len(targets)} existing accounts; no writes or permission tests.")
    else:
        completed = sum(account in rule["created_exemptions"] for account in targets)
        excluded = sum(account in rule["excluded_accounts"] for account in targets)
        if completed + excluded != len(targets):
            raise ContextError("Not every approved account has an exemption or explicit protected exclusion.")
        print(f"Storage exemption check: PASS ({completed} verified; {excluded} approved protected exclusions).")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"Storage exemption blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
