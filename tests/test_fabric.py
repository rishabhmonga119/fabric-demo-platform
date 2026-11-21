import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fabric_preflight
import http_api
from bootstrap_entra import has_membership
from bootstrap_fabric import domain_role_plan, setting_proposal
from check_demo_licenses import license_features


class FabricPaginationTests(unittest.TestCase):
    def test_token_pagination_preserves_filters_and_exhausts_results(self):
        responses = [
            json.dumps({"workspaces": [{"id": "first"}], "continuationToken": "opaque+/=%"}),
            json.dumps({"workspaces": [{"id": "second"}]}),
        ]
        with patch.object(fabric_preflight, "cli", return_value="az"):
            with patch.object(fabric_preflight, "run", side_effect=responses) as run:
                rows = fabric_preflight.fabric_list(
                    "/v1/admin/workspaces?type=Workspace&state=Active", "workspaces"
                )
                self.assertEqual(rows, [{"id": "first"}, {"id": "second"}])
                command = run.call_args.args[0]
                query = parse_qs(urlparse(command[command.index("--url") + 1]).query)
                self.assertEqual(query["type"], ["Workspace"])
                self.assertEqual(query["state"], ["Active"])
                self.assertEqual(query["continuationToken"], ["opaque+/=%"])

    def test_unexpected_continuation_origin_is_rejected_before_authentication(self):
        response = json.dumps({
            "value": [], "continuationUri": "https://unexpected.example/next"
        })
        with patch.object(fabric_preflight, "cli", return_value="az"):
            with patch.object(fabric_preflight, "run", return_value=response) as run:
                with self.assertRaisesRegex(RuntimeError, "unexpected Fabric pagination origin"):
                    fabric_preflight.fabric_list("/v1/capacities", "value")
                self.assertEqual(run.call_count, 1)


class JsonApiGuardTests(unittest.TestCase):
    def test_dry_run_never_acquires_credentials_or_sends_secret_payload(self):
        with patch.object(http_api, "AzureCliCredential") as credential, \
             patch.object(http_api, "build_opener") as opener, \
             patch.object(http_api, "verify_context") as context:
            api = http_api.Api("https://graph.microsoft.com", "demo")
            api.request("POST", "/v1.0/users", {"passwordProfile": {"password": "not-a-real-secret"}},
                        dry_run=True)
            context.assert_called_once()
            credential.return_value.get_token.assert_not_called()
            opener.return_value.open.assert_not_called()

    def test_unknown_origin_is_rejected_before_token_acquisition(self):
        with patch.object(http_api, "AzureCliCredential") as credential:
            api = http_api.Api("https://graph.microsoft.com", "demo")
            with self.assertRaisesRegex(RuntimeError, "unexpected API origin"):
                api.request("GET", "https://unexpected.example/user")
            credential.return_value.get_token.assert_not_called()

    def test_accepted_async_response_is_not_reported_as_completed(self):
        response = MagicMock()
        response.status = 202
        response.read.return_value = b'{"status":"Running"}'
        with patch.object(http_api, "AzureCliCredential"), \
             patch.object(http_api, "build_opener") as opener, \
             patch.object(http_api, "verify_context"):
            opener.return_value.open.return_value.__enter__.return_value = response
            api = http_api.Api("https://api.fabric.microsoft.com", "demo",
                               skill="onelake-catalog-cli")
            with self.assertRaisesRegex(http_api.ApiError, "requires documented LRO"):
                api.request("POST", "/v1/workspaces")


class GroupMembershipTests(unittest.TestCase):
    def test_membership_check_supports_service_principals_without_member_listing(self):
        api = MagicMock()
        api.request.return_value = {"value": ["target-group"]}
        self.assertTrue(has_membership(api, "target-group", "service-principal"))
        api.request.assert_called_once_with(
            "POST", "/v1.0/directoryObjects/service-principal/checkMemberGroups",
            {"groupIds": ["target-group"]}
        )
        api.list.assert_not_called()

    def test_missing_membership_and_invalid_response_are_not_success(self):
        api = MagicMock()
        api.request.return_value = {"value": []}
        self.assertFalse(has_membership(api, "target-group", "member"))
        api.request.return_value = {}
        with self.assertRaises(http_api.ApiError):
            has_membership(api, "target-group", "member")


class TenantSettingProposalTests(unittest.TestCase):
    def test_scope_change_preserves_unrelated_settings_and_does_not_mutate_snapshot(self):
        current = {
            "enabled": False, "canSpecifySecurityGroups": True,
            "delegateToCapacity": True, "excludedSecurityGroups": [{"graphId": "excluded"}],
            "properties": [{"name": "existing", "value": "true", "type": "Boolean"}],
        }
        allowed = [{"graphId": "demo", "name": "Demo admins"}]
        proposed = setting_proposal(current, allowed)
        self.assertTrue(proposed["enabled"])
        self.assertEqual(proposed["enabledSecurityGroups"], allowed)
        self.assertEqual(proposed["excludedSecurityGroups"], current["excludedSecurityGroups"])
        self.assertEqual(proposed["properties"], current["properties"])
        self.assertFalse(current["enabled"])
        self.assertNotIn("enabledSecurityGroups", current)

    def test_unscopable_setting_is_not_enabled_tenant_wide(self):
        with self.assertRaises(RuntimeError):
            setting_proposal({"enabled": False, "canSpecifySecurityGroups": False}, [])


class DomainRolePlanTests(unittest.TestCase):
    def test_same_owner_and_contributor_group_is_not_downgraded(self):
        group = {"id": "admins", "name": "Demo admins"}
        domain = {"administrator_group": "Demo admins", "contributor_group": "Demo admins"}
        self.assertEqual(domain_role_plan(domain, {"admins": group}), [("Admin", "Admins", group)])

    def test_separate_contributor_group_keeps_its_narrower_role(self):
        admin = {"id": "admins", "name": "Demo admins"}
        contributor = {"id": "contributors", "name": "Demo contributors"}
        domain = {"administrator_group": "Demo admins", "contributor_group": "Demo contributors"}
        self.assertEqual(
            domain_role_plan(domain, {"admins": admin, "contributors": contributor}),
            [("Admin", "Admins", admin), ("Contributor", "Contributors", contributor)]
        )


class LicenseFeatureTests(unittest.TestCase):
    def test_new_sku_names_are_supported_by_their_actual_service_plans(self):
        features = license_features({
            "BI_AZURE_P2", "M365_COPILOT_APPS", "M365_COPILOT_TEAMS",
            "M365_COPILOT_BUSINESS_CHAT", "OTHER_SERVICE"
        })
        self.assertEqual(features, {"power_bi_pro": True, "m365_copilot": True})
        self.assertEqual(
            license_features({"COPILOT_CREDIT_FOR_D365_PREMIUM"}),
            {"power_bi_pro": False, "m365_copilot": False}
        )


if __name__ == "__main__":
    unittest.main()
