import copy
import json
import unittest
from unittest.mock import patch

from infra import deploy
from infra import exempt_storage_policy
from tools.common import ContextError


CONFIG = {
    "azure": {"storage_account_name": "demo-storage", "resource_group": "demo-group"},
    "github": {"owner": "demo-owner", "repository": "demo-repo"},
}
STORAGE = {
    "tags": {"demoOwner": "demo-owner/demo-repo", "createdBy": "copilot-demo-build"},
    "publicNetworkAccess": "Disabled",
    "allowBlobPublicAccess": False,
}


class NetworkGuardTests(unittest.TestCase):
    def setUp(self):
        patch.object(deploy, "cli", return_value="az").start()
        patch.object(deploy, "record").start()
        self.addCleanup(patch.stopall)

    def test_unowned_account_never_receives_a_network_write(self):
        storage = copy.deepcopy(STORAGE)
        storage["tags"] = {}
        with patch.object(deploy, "run", return_value=json.dumps(storage)):
            with patch.object(deploy, "mutate") as mutate:
                with self.assertRaises(ContextError):
                    deploy.ensure_storage_network(CONFIG)
                mutate.assert_not_called()

    def test_failed_or_unsafe_network_update_is_not_reported_as_success(self):
        unsafe = copy.deepcopy(STORAGE)
        unsafe["publicNetworkAccess"] = "Enabled"
        unsafe["allowBlobPublicAccess"] = True
        for after in (STORAGE, unsafe):
            with self.subTest(after=after), patch.object(
                deploy, "run", side_effect=[json.dumps(STORAGE), json.dumps(after)]
            ), patch.object(deploy, "mutate"):
                with self.assertRaisesRegex(RuntimeError, "Storage network verification failed"):
                    deploy.ensure_storage_network(CONFIG)

    def test_network_dry_run_does_not_write_or_poll_for_changes(self):
        with patch.object(deploy, "run", return_value=json.dumps(STORAGE)) as run:
            with patch.object(deploy, "mutate") as mutate:
                deploy.ensure_storage_network(CONFIG, dry_run=True)
                self.assertEqual(run.call_count, 1)
                self.assertTrue(mutate.call_args.args[1])
                deploy.record.assert_not_called()

    def test_arm_dry_run_does_not_create_a_payload_file(self):
        storage = copy.deepcopy(STORAGE)
        storage["id"] = "/subscriptions/demo/resourceGroups/demo/providers/Microsoft.Storage/storageAccounts/demo"
        with patch.object(deploy, "run", return_value=json.dumps(storage)):
            with patch.object(deploy, "mutate") as mutate:
                with patch.object(deploy.tempfile, "TemporaryDirectory") as temporary:
                    deploy.ensure_storage_network(CONFIG, dry_run=True, method="arm")
                    temporary.assert_not_called()
                    self.assertTrue(mutate.call_args.kwargs["dry_run"])


class ExemptionGuardTests(unittest.TestCase):
    def test_only_explicitly_approved_platform_denials_can_be_excluded(self):
        account = "/subscriptions/demo/resourceGroups/demo/providers/Microsoft.Storage/storageAccounts/demo"
        for approved, message in (
            (True, "DenyAssignmentAuthorizationFailed"),
            (False, "DenyAssignmentAuthorizationFailed"),
            (True, "AuthorizationFailed"),
        ):
            config = {
                "azure": {"subscription_id": "demo", "storage_policy_exemption": {
                    "name": "demo", "assignment_id": "/policyAssignments/demo",
                    "definition_reference_id": "public-network",
                    "target_resource_ids": [account], "created_exemptions": {},
                    "excluded_accounts": {}, "exclude_platform_denied": approved,
                }},
                "github": {"owner": "demo-owner", "repository": "demo-repo"},
            }
            with self.subTest(approved=approved, message=message):
                with patch.object(exempt_storage_policy, "load_config", return_value=config), \
                     patch.object(exempt_storage_policy, "verify_context"), \
                     patch.object(exempt_storage_policy, "cli", return_value="az"), \
                     patch.object(exempt_storage_policy, "run",
                                  side_effect=[json.dumps([{"id": account}]), "[]"]), \
                     patch.object(exempt_storage_policy, "mutate",
                                  side_effect=ContextError(message)), \
                     patch.object(exempt_storage_policy, "save_config"), \
                     patch.object(exempt_storage_policy, "record"), \
                     patch("sys.argv", ["exempt_storage_policy.py"]):
                    if approved and message == "DenyAssignmentAuthorizationFailed":
                        exempt_storage_policy.main()
                        self.assertEqual(
                            config["azure"]["storage_policy_exemption"]["excluded_accounts"],
                            {account: message},
                        )
                    else:
                        with self.assertRaises(ContextError):
                            exempt_storage_policy.main()
                        self.assertEqual(
                            config["azure"]["storage_policy_exemption"]["excluded_accounts"], {}
                        )

    def test_unowned_or_broader_exemption_is_rejected(self):
        account = "/subscriptions/demo/resourceGroups/demo/providers/Microsoft.Storage/storageAccounts/demo"
        rule = {"name": "demo-exemption", "assignment_id": "/policyAssignments/demo",
                "definition_reference_id": "public-network"}
        valid = {
            "id": f"{account}/providers/Microsoft.Authorization/policyExemptions/demo-exemption",
            "policyAssignmentId": "/policyAssignments/demo",
            "policyDefinitionReferenceIds": ["public-network"],
            "exemptionCategory": "Waiver",
            "metadata": {"demoOwner": "demo-owner/demo-repo", "createdBy": "copilot-demo-build"},
        }
        exempt_storage_policy.verify_exemption(valid, account, rule, "demo-owner/demo-repo")
        changes = [
            ("id", "/subscriptions/demo/providers/Microsoft.Authorization/policyExemptions/demo-exemption"),
            ("policyDefinitionReferenceIds", []),
            ("policyDefinitionReferenceIds", ["public-network", "anonymous-access"]),
            ("policyAssignmentId", "/policyAssignments/other"),
            ("metadata", None),
        ]
        for key, value in changes:
            exemption = copy.deepcopy(valid)
            exemption[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ContextError):
                    exempt_storage_policy.verify_exemption(exemption, account, rule, "demo-owner/demo-repo")


if __name__ == "__main__":
    unittest.main()
