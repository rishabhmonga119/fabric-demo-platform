import copy
import json
import os
import subprocess
import unittest
from base64 import urlsafe_b64encode
from unittest.mock import MagicMock, patch

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


class MetadataCiTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            **CONFIG,
            "github": {"owner": "demo-owner", "repository": "demo-repo", "branch": "main",
                       "owner_id": 11, "repository_id": 22},
            "entra": {"application": {"client_id": "demo-app", "service_principal_id": "demo-sp"}},
            "fabric": {"capacity_id": "demo-capacity"},
            "environments": {"test": {"workspace_id": "test-workspace"},
                             "prod": {"workspace_id": "prod-workspace"}},
        }
        self.environment = {
            "FABRIC_METADATA_CI": "true", "FABRIC_DEPLOY_STAGE": "prod",
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "demo-owner/demo-repo",
            "GITHUB_ACTOR": "demo-owner", "GITHUB_ACTOR_ID": "11", "GITHUB_REF": "refs/heads/main",
            "AZURE_CLIENT_ID": "demo-app", "AZURE_TENANT_ID": "demo-tenant",
            "FABRIC_CAPACITY_ID": "demo-capacity",
        }
        patch.dict(os.environ, self.environment).start()
        patch.object(common, "load_config", return_value=self.config).start()
        patch.object(common, "cli", side_effect=lambda name: name).start()
        self.addCleanup(patch.stopall)

    def test_oidc_checks_actual_application_and_immutable_repository_identity(self):
        account = {"tenantId": "demo-tenant", "user": {"name": "demo-app", "type": "servicePrincipal"}}
        claims = {"tid": "demo-tenant", "appid": "demo-app", "oid": "demo-sp"}
        token = "header." + urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".signature"
        credential = MagicMock()
        credential.get_token.return_value.token = token
        with patch("azure.identity.AzureCliCredential", return_value=credential), \
                patch.object(common, "run", side_effect=[
                    json.dumps(account), json.dumps({"id": 22, "owner": {"id": 11}})]) as run:
            common.verify_context()
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("fab", [call.args[0][0] for call in run.call_args_list])

    def test_untrusted_workflow_context_cannot_enable_ci_exception(self):
        for name, value in (("GITHUB_ACTIONS", "false"), ("GITHUB_REF", "refs/heads/other"),
                            ("GITHUB_ACTOR_ID", "99"), ("GITHUB_REPOSITORY", "other/repo")):
            with self.subTest(name=name), patch.dict(os.environ, {name: value}), \
                    patch.object(common, "run") as run:
                with self.assertRaises(common.ContextError):
                    common.verify_context()
                run.assert_not_called()

    def test_wrong_fabric_principal_stops_before_repository_access(self):
        account = {"tenantId": "demo-tenant", "user": {"name": "demo-app", "type": "servicePrincipal"}}
        claims = {"tid": "demo-tenant", "appid": "demo-app", "oid": "other-sp"}
        token = "header." + urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".signature"
        credential = MagicMock()
        credential.get_token.return_value.token = token
        with patch("azure.identity.AzureCliCredential", return_value=credential), \
                patch.object(common, "run", return_value=json.dumps(account)) as run:
            with self.assertRaises(common.ContextError):
                common.verify_context()
            self.assertEqual(run.call_count, 1)

    def test_ci_cannot_refresh_grant_delete_or_access_another_stage(self):
        for method, url, payload in (
            ("POST", "https://api.fabric.microsoft.com/v1/workspaces/prod-workspace/items/p/jobs/instances", {}),
            ("POST", "https://api.fabric.microsoft.com/v1/workspaces/prod-workspace/roleAssignments", {}),
            ("DELETE", "https://api.fabric.microsoft.com/v1/workspaces/prod-workspace/items/p", None),
            ("POST", "https://api.fabric.microsoft.com/v1/workspaces/test-workspace/reports/p/updateDefinition", {}),
            ("POST", "https://api.fabric.microsoft.com/v1/workspaces/prod-workspace/items", {"type": "Lakehouse"}),
            ("GET", "https://graph.microsoft.com/v1.0/users", None),
        ):
            with self.subTest(url=url), self.assertRaises(common.ContextError):
                common.verify_metadata_request(method, url, payload)

    def test_readonly_preflight_can_get_definitions_but_cannot_publish(self):
        root = "https://api.fabric.microsoft.com/v1/workspaces/prod-workspace/reports/r/"
        with patch.dict(os.environ, {"FABRIC_METADATA_READ_ONLY": "true"}):
            common.verify_metadata_request("POST", root + "getDefinition", {})
            with self.assertRaises(common.ContextError):
                common.verify_metadata_request("POST", root + "updateDefinition", {})
        common.verify_metadata_request("POST", root + "updateDefinition", {})


if __name__ == "__main__":
    unittest.main()
