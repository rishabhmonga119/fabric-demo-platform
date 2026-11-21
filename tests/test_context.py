import copy
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from tools import common


CONFIG = {
    "tenant": {"id": "demo-tenant", "admin_upn": "admin@demo.onmicrosoft.com"},
    "azure": {"subscription_id": "demo-subscription"},
    "github": {"owner": "demo-owner"},
}
AZURE = {
    "tenantId": "demo-tenant",
    "id": "demo-subscription",
    "user": {"name": "admin@demo.onmicrosoft.com", "type": "user"},
}
FABRIC = (
    "Logged In: True\nAccount: admin@demo.onmicrosoft.com\nTenant ID: demo-tenant\n"
)
GITHUB = (
    "Logged in to github.com account demo-owner (keyring)\n"
    "  - Active account: true\n"
)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.object(common, "load_config", return_value=CONFIG).start()
        self.cli = patch.object(common, "cli", side_effect=lambda name: name).start()
        self.addCleanup(patch.stopall)

    def test_wrong_azure_context_stops_before_other_services(self):
        for field in ("tenantId", "id", "user"):
            account = copy.deepcopy(AZURE)
            account[field] = {"name": "other-user", "type": "user"} if field == "user" else "other"
            with self.subTest(field=field), patch.object(
                common, "run", return_value=json.dumps(account)
            ) as run:
                with self.assertRaises(common.ContextError):
                    common.verify_context()
                self.assertEqual(run.call_count, 1)

    def test_fabric_identity_must_be_present_unique_and_correct(self):
        invalid = [
            FABRIC.replace("Logged In: True", "Logged In: False"),
            FABRIC.replace("admin@demo", "other@demo"),
            FABRIC.replace("Tenant ID: demo-tenant\n", ""),
            FABRIC + "Tenant ID: other-tenant\n",
        ]
        for status in invalid:
            with self.subTest(status=status), patch.object(
                common, "run", side_effect=[json.dumps(AZURE), status]
            ) as run:
                with self.assertRaises(common.ContextError):
                    common.verify_context()
                self.assertEqual(run.call_count, 2)

    def test_wrong_or_inactive_github_account_blocks_mutation(self):
        for status in (
            GITHUB.replace("demo-owner", "other-owner"),
            GITHUB.replace("true", "false"),
        ):
            with self.subTest(status=status), patch.object(
                common, "run", side_effect=[json.dumps(AZURE), FABRIC, status]
            ) as run:
                with self.assertRaises(common.ContextError):
                    common.mutate(["gh", "api", "--method", "POST"])
                self.assertEqual(run.call_count, 3)

    def test_dry_run_checks_context_but_never_executes_mutation(self):
        with patch.object(
            common, "run", side_effect=[json.dumps(AZURE), FABRIC, GITHUB]
        ) as run:
            common.mutate(["gh", "api", "--method", "POST"], dry_run=True)
            self.assertEqual(run.call_count, 3)


class AzureInvocationTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows Azure CLI wrapper regression")
    def test_query_metacharacters_are_passed_to_native_azure_cli(self):
        endpoint = "https://api.fabric.microsoft.com/v1/admin/workspaces?type=Workspace&state=Active"
        result = subprocess.CompletedProcess([], 0, "{}", "")
        with patch.object(common.Path, "is_file", return_value=True):
            with patch.object(common.subprocess, "run", return_value=result) as run:
                common.run([r"C:\Azure\CLI2\wbin\az.cmd", "rest", "--url", endpoint])
                execution = run.call_args.args[0]
                self.assertEqual(execution[0], r"C:\Azure\CLI2\python.exe")
                self.assertEqual(execution[1:3], ["-IBm", "azure.cli"])
                self.assertEqual(execution[-1], endpoint)
                self.assertEqual(run.call_args.kwargs["env"]["AZ_INSTALLER"], "MSI")


if __name__ == "__main__":
    unittest.main()
