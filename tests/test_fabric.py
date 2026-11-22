import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fabric_preflight
import http_api
from bootstrap_entra import federation_subjects, has_membership
from bootstrap_fabric import domain_role_plan, setting_proposal
from check_demo_licenses import license_features
from select_test_users import assert_viewer_eligible
from bootstrap_fabric_items import create_lakehouse


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
    def test_powerbi_regional_refresh_location_uses_public_origin_and_correct_audience(self):
        response = MagicMock()
        response.status = 202
        response.read.return_value = b""
        path = "/v1.0/myorg/groups/workspace/datasets/model/refreshes"
        refresh_id = "e97dcbb5-2d8e-4b01-b1e0-1ad98d186839"
        response.headers.get.side_effect = lambda name: {
            "Location": "https://regional.example" + path + "/" + refresh_id
        }.get(name)
        with patch.object(http_api, "AzureCliCredential") as credential, \
             patch.object(http_api, "build_opener") as opener, \
             patch.object(http_api, "verify_context"):
            opener.return_value.open.return_value.__enter__.return_value = response
            api = http_api.Api("https://api.powerbi.com", "demo")
            self.assertEqual(api.request("POST", path, {}, accept_operation=True),
                             {"operation_uri": "https://api.powerbi.com" + path + "/" + refresh_id})
            credential.return_value.get_token.assert_called_once_with(
                "https://analysis.windows.net/powerbi/api/.default")
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_powerbi_refresh_location_cannot_switch_resources(self):
        response = MagicMock()
        response.status = 202
        response.read.return_value = b""
        response.headers.get.return_value = (
            "https://regional.example/v1.0/myorg/groups/other/datasets/model/refreshes/"
            "e97dcbb5-2d8e-4b01-b1e0-1ad98d186839")
        with patch.object(http_api, "AzureCliCredential"), \
             patch.object(http_api, "build_opener") as opener, \
             patch.object(http_api, "verify_context"):
            opener.return_value.open.return_value.__enter__.return_value = response
            api = http_api.Api("https://api.powerbi.com", "demo")
            with self.assertRaisesRegex(http_api.ApiError, "same-origin Location"):
                api.request("POST", "/v1.0/myorg/groups/workspace/datasets/model/refreshes",
                            {}, accept_operation=True)

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

    def test_explicit_operation_acceptance_requires_same_origin_location(self):
        response = MagicMock()
        response.status = 202
        response.read.return_value = b""
        with patch.object(http_api, "AzureCliCredential"), \
             patch.object(http_api, "build_opener") as opener, \
             patch.object(http_api, "verify_context"):
            opener.return_value.open.return_value.__enter__.return_value = response
            api = http_api.Api("https://graph.microsoft.com", "demo")
            response.headers.get.return_value = "https://graph.microsoft.com/beta/sites/operation"
            self.assertEqual(api.request("POST", "/beta/sites", accept_operation=True),
                             {"operation_uri": "https://graph.microsoft.com/beta/sites/operation"})
            response.headers.get.return_value = "/beta/sites/operation"
            self.assertEqual(api.request("POST", "/beta/sites", accept_operation=True),
                             {"operation_uri": "https://graph.microsoft.com/beta/sites/operation"})
            for location in (None, "https://unexpected.example/operation"):
                response.headers.get.return_value = location
                with self.assertRaisesRegex(http_api.ApiError, "same-origin Location"):
                    api.request("POST", "/beta/sites", accept_operation=True)

    def test_binary_upload_bytes_are_not_json_encoded(self):
        response = MagicMock()
        response.status = 201
        response.read.return_value = b'{"id":"uploaded"}'
        with patch.object(http_api, "AzureCliCredential"), \
             patch.object(http_api, "build_opener") as opener, \
             patch.object(http_api, "verify_context"):
            opener.return_value.open.return_value.__enter__.return_value = response
            api = http_api.Api("https://graph.microsoft.com", "demo")
            api.request("PUT", "/v1.0/drives/demo/items/new/content", b"PK\x00\x01",
                        content_type="application/octet-stream")
            self.assertEqual(opener.return_value.open.call_args.args[0].data, b"PK\x00\x01")

    def test_lro_response_info_preserves_retry_after_without_changing_default_body(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":"Running"}'
        response.headers.get.return_value = "30"
        with patch.object(http_api, "AzureCliCredential"), \
             patch.object(http_api, "build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = response
            api = http_api.Api("https://api.fabric.microsoft.com", "demo", skill="e2e-medallion-architecture")
            self.assertEqual(api.request("GET", "/v1/operations/op"), {"status": "Running"})
            self.assertEqual(api.request("GET", "/v1/operations/op", with_response_info=True),
                             {"status_code": 200, "retry_after": "30", "body": {"status": "Running"}})


class LakehouseLroTests(unittest.TestCase):
    def test_create_waits_for_terminal_success_and_honors_each_retry_after(self):
        api = MagicMock()
        api.request.side_effect = [
            {"status_code": 202, "retry_after": "30", "body": {"operation_uri": "https://api.fabric.microsoft.com/v1/operations/op"}},
            {"status_code": 200, "retry_after": "10", "body": {"status": "Running"}},
            {"status_code": 200, "retry_after": None, "body": {"status": "Succeeded"}},
            {"id": "created-lakehouse"},
        ]
        with patch("bootstrap_fabric_items.time.sleep") as sleep:
            self.assertEqual(create_lakehouse(api, "workspace", "LH_Landing", "owned", False),
                             {"id": "created-lakehouse"})
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [30, 10])
            api.request.assert_called_with("GET", "https://api.fabric.microsoft.com/v1/operations/op/result")


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


class FederationSubjectTests(unittest.TestCase):
    def test_immutable_subjects_match_owner_repository_and_environment_ids(self):
        repository = {"full_name": "owner/repo", "owner": {"id": 10}, "id": 20}
        oidc = {"use_default": True, "use_immutable_subject": True,
                "sub_claim_prefix": "repo:owner@10/repo@20"}
        subjects = federation_subjects(repository, oidc)
        self.assertEqual(subjects["github-test"], "repo:owner@10/repo@20:environment:test")
        self.assertEqual(subjects["github-main"], "repo:owner@10/repo@20:ref:refs/heads/main")

    def test_other_repository_prefix_is_never_trusted(self):
        with self.assertRaises(RuntimeError):
            federation_subjects(
                {"full_name": "owner/repo", "owner": {"id": 10}, "id": 20},
                {"use_default": True, "use_immutable_subject": True,
                 "sub_claim_prefix": "repo:other@10/repo@20"}
            )


class ViewerEligibilityTests(unittest.TestCase):
    def test_viewer_role_is_valid_but_privileged_group_membership_is_rejected(self):
        assignments = [
            {"role": "Viewer", "principal": {"id": "sales", "type": "Group"}},
            {"role": "Admin", "principal": {"id": "admins", "type": "Group"}},
        ]
        assert_viewer_eligible("test-user", assignments, {"sales"})
        with self.assertRaisesRegex(RuntimeError, "bypasses OneLake security"):
            assert_viewer_eligible("test-user", assignments, {"sales", "admins"})

    def test_direct_privileged_or_entire_tenant_access_is_rejected(self):
        for principal in (
            {"id": "test-user", "type": "User"},
            {"id": "tenant", "type": "EntireTenant"},
        ):
            with self.subTest(principal=principal), self.assertRaises(RuntimeError):
                assert_viewer_eligible(
                    "test-user", [{"role": "Contributor", "principal": principal}], set()
                )


if __name__ == "__main__":
    unittest.main()
