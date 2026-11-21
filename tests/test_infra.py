import copy
import json
import unittest
from unittest.mock import patch

from infra import deploy
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


if __name__ == "__main__":
    unittest.main()
