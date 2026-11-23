from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from partner_logic import PARTNER_COLUMNS, partner_deliveries


class PartnerProjectionTests(unittest.TestCase):
    def setUp(self):
        self.products = [{"sku": "sku", "product_name": "Mineral water", "env_marker": "prod"}]
        self.row = {"month": date(2026, 10, 1), "sku": "sku", "partner_id": "P-A",
                    "package_code": "pack", "region_code": "NORTH", "delivered_hl": "12.34",
                    "on_time_pct": "98.99", "env_marker": "prod", "revenue": "999"}

    def test_only_pa_rows_and_exact_nonfinancial_projection_preserve_delivery_grain(self):
        rows = [self.row, {**self.row, "partner_id": "P-B", "delivered_hl": "1000"},
                {**self.row, "region_code": "EAST", "delivered_hl": "2.00"}]
        original = deepcopy(rows)
        result = partner_deliveries(rows, self.products)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(tuple(row) == PARTNER_COLUMNS for row in result))
        self.assertEqual(sum(row["delivered_hl"] for row in result), Decimal("14.34"))
        self.assertEqual(result[0]["product_name"], "Mineral water")
        self.assertEqual(rows, original)

    def test_duplicate_or_missing_product_and_mixed_stage_sources_are_rejected(self):
        cases = [
            ([self.row], self.products * 2),
            ([{**self.row, "sku": "missing"}], self.products),
            ([{**self.row, "env_marker": "test"}], self.products),
            ([self.row], [{**self.products[0], "env_marker": "dev"}]),
            ([{**self.row, "partner_id": "P-B"}], self.products),
        ]
        for rows, products in cases:
            with self.subTest(rows=rows, products=products), self.assertRaises(ValueError):
                partner_deliveries(rows, products)

    def test_invalid_month_volume_and_percentage_are_rejected(self):
        for changes in ({"month": date(2026, 10, 2)}, {"delivered_hl": "-0.01"},
                        {"on_time_pct": "100.01"}, {"delivered_hl": "NaN"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                partner_deliveries([{**self.row, **changes}], self.products)


class PartnerExecutionTests(unittest.TestCase):
    def test_auto_created_sql_endpoint_name_does_not_conflict_with_owned_lakehouse(self):
        from bootstrap_partner import MARKER, owned_item
        from common import ContextError
        lakehouse = {"id": "lakehouse", "type": "Lakehouse", "displayName": "LH_PartnerA",
                     "description": MARKER}
        endpoint = {"id": "endpoint", "type": "SQLEndpoint", "displayName": "LH_PartnerA",
                    "description": ""}
        partner = {"items": {"LH_PartnerA": {"id": "lakehouse"}}}
        self.assertEqual(owned_item([endpoint, lakehouse], partner, "LH_PartnerA", "Lakehouse"),
                         lakehouse)
        with self.assertRaises(ContextError):
            owned_item([lakehouse, lakehouse], partner, "LH_PartnerA", "Lakehouse")
        with self.assertRaises(ContextError):
            owned_item([{**lakehouse, "description": ""}], partner, "LH_PartnerA", "Lakehouse")

    def test_completed_job_metrics_support_real_nested_response_and_enforce_exact_baseline(self):
        from bootstrap_partner import verification_metrics
        from http_api import ApiError
        metrics = {
            "check": "PASS", "table": "dbo.partner_a_deliveries", "rows": 1232,
            "columns": list(PARTNER_COLUMNS), "delivered_hl": "1121803.72",
            "min_month": "2025-01-01", "max_month": "2026-10-01", "regions": ["EAST", "NORTH"],
            "exact_filtered_row_readback": True, "glossary_readback": True,
        }
        for response in ({"exitValue": json.dumps(metrics)},
                         {"properties": {"exitValue": json.dumps(metrics)}}):
            self.assertEqual(verification_metrics(
                {"status": "Completed", **response}, initial_baseline=True), metrics)
        for change in ({"rows": 1233}, {"delivered_hl": "1121803.73"},
                       {"columns": list(PARTNER_COLUMNS) + ["margin"]},
                       {"exact_filtered_row_readback": False}):
            with self.subTest(change=change), self.assertRaises(ApiError):
                verification_metrics({"status": "Completed",
                                      "properties": {"exitValue": json.dumps({**metrics, **change})}},
                                     initial_baseline=True)
        with self.assertRaises(ApiError):
            verification_metrics({"status": "Completed"}, initial_baseline=True)

    def test_notebook_payload_is_valid_pure_python_and_bound_to_partner_not_prod(self):
        import bootstrap_partner
        notebook = bootstrap_partner.make_notebook({
            "tenant": {"id": "tenant", "admin_object_id": "admin"},
            "partner": {"workspace_name": "Partner", "workspace_id": "partner-workspace",
                        "items": {"LH_PartnerA": {"id": "partner-lakehouse"}}},
            "environments": {"prod": {"workspace_id": "prod-workspace",
                                       "items": {"LH_Curated": {"id": "prod-curated"}}}},
        })
        self.assertEqual(notebook.metadata["kernel_info"]["name"], "jupyter")
        self.assertEqual(notebook.metadata["dependencies"]["lakehouse"]["default_lakehouse"],
                         "partner-lakehouse")
        self.assertIn("prod-curated", notebook.cells[0].source)
        for index, cell in enumerate(notebook.cells):
            compile(cell.source, f"cell-{index}", "exec")

    def test_shared_runner_preserves_pipeline_route_and_monitors_notebook_without_duplicate(self):
        import bootstrap_refresh_pipeline as runner
        for name, kind, active in (("PL_Refresh", "Pipeline", []),
                                   ("NB_Partner_Extract", "RunNotebook",
                                    [{"id": "active", "status": "Running"}])):
            with self.subTest(kind=kind), patch.object(runner, "save_config"), \
                    patch.object(runner, "record"), patch.object(runner.time, "sleep"):
                api = MagicMock(base="https://api.fabric.microsoft.com")
                api.list.return_value = active
                completed = {"status": "Completed", "exitValue": "verified"}
                api.request.side_effect = [completed] if active else [
                    {"body": {"operation_uri": "https://api.fabric.microsoft.com/jobs/new"},
                     "retry_after": "0"}, completed]
                stage = {"workspace_id": "workspace", "workspace_name": "Partner",
                         "items": {name: {}}}
                if kind == "Pipeline":
                    runner.run_pipeline(api, {}, stage, {"id": "item"}, False)
                    self.assertIn("jobType=Pipeline", api.request.call_args_list[0].args[1])
                else:
                    result = runner.run_item_job(
                        api, {}, stage, {"id": "item"}, False, name=name, job_type=kind,
                        definition_sha256="digest")
                    self.assertEqual(result, completed)
                    self.assertTrue(all(call.args[0] == "GET" for call in api.request.call_args_list))
                self.assertEqual(stage["items"][name]["last_run_state"], "Completed")

    def test_recent_completed_notebook_content_is_reused_without_another_submission(self):
        from datetime import datetime, timezone
        import bootstrap_refresh_pipeline as runner
        api = MagicMock()
        api.list.return_value = [{"id": "recent", "status": "Completed",
                                  "startTimeUtc": datetime.now(timezone.utc).isoformat()}]
        stage = {"workspace_id": "workspace", "items": {"NB_Partner_Extract": {
            "last_run_id": "recent", "last_run_definition_sha256": "digest"}}}
        runner.run_item_job(api, {}, stage, {"id": "item"}, False, name="NB_Partner_Extract",
                            job_type="RunNotebook", definition_sha256="digest")
        api.request.assert_called_once_with(
            "GET", "/v1/workspaces/workspace/items/item/jobs/instances/recent")


class PartnerShareTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "tenant": {"id": "11111111-1111-4111-8111-111111111111"},
            "partner": {
                "tenant_b_id": "22222222-2222-4222-8222-222222222222",
                "tenant_b_domain": "partner.example", "workspace_id": "partner-workspace",
                "recipient_upn_env": "FABRIC_PARTNER_RECIPIENT_UPN",
                "items": {"LH_PartnerA": {"id": "output-lakehouse"}},
            },
        }

    def test_share_is_one_output_asset_and_cross_tenant_recipient_with_explicit_expiry(self):
        from manage_partner_share import canonical, share_document
        from common import ContextError
        document = share_document(self.config, "user@partner.example", "2099-01-01T00:00:00Z")
        self.assertEqual(len(document["assets"]), 1)
        self.assertEqual(document["assets"][0]["item"]["itemId"], "output-lakehouse")
        self.assertEqual(document["recipients"], [{
            "type": "User", "userPrincipalName": "user@partner.example",
            "tenantId": self.config["partner"]["tenant_b_id"]}])
        self.assertEqual(document["sharePolicies"][0]["properties"]["expirationDateTime"],
                         "2099-01-01T00:00:00Z")
        exported = deepcopy(document)
        exported["assets"][0].pop("shareAs")
        exported["assets"][0]["item"].pop("referenceType")
        self.assertEqual(canonical(document), canonical(exported))
        with self.assertRaises(ContextError):
            share_document(self.config, "different@other.example", "2099-01-01T00:00:00Z")
        self.config["partner"]["tenant_b_id"] = self.config["tenant"]["id"]
        with self.assertRaises(ContextError):
            share_document(self.config, "user@partner.example", "2099-01-01T00:00:00Z")

    def test_whole_item_guard_rejects_extra_tables_files_or_missing_delta_log(self):
        from manage_partner_share import guard_shared_inventory
        from common import ContextError
        table = "lakehouse/Tables/dbo/partner_a_deliveries"
        paths = {table, table + "/_delta_log", table + "/_delta_log/00000000000000000000.json",
                 table + "/part.parquet"}
        files = {"lakehouse/Files/context/partner_glossary.md"}
        guard_shared_inventory(paths, files, "lakehouse")
        for tables, shared_files in (
                (paths | {"lakehouse/Tables/dbo/all_deliveries"}, files),
                (paths, files | {"lakehouse/Files/raw.csv"}), ({table + "/part.parquet"}, files),
                (set(), files)):
            with self.subTest(tables=tables, files=shared_files), self.assertRaises(ContextError):
                guard_shared_inventory(tables, shared_files, "lakehouse")

    def test_unapproved_share_never_constructs_an_authenticated_api_client(self):
        import manage_partner_share as share
        with patch.object(sys, "argv", ["manage_partner_share.py", "create",
                                       "--expires-utc", "2099-01-01T00:00:00Z"]), \
                patch.object(share, "is_metadata_ci", return_value=False), \
                patch.object(share, "verify_context"), \
                patch.object(share, "load_config", return_value=self.config), \
                patch.dict(share.os.environ, {"FABRIC_PARTNER_RECIPIENT_UPN": "user@partner.example"}), \
                patch.object(share, "Api") as api, self.assertRaises(share.ContextError):
            try:
                share.main()
            finally:
                api.assert_not_called()

    def test_live_powerbi_invitation_is_bound_to_exact_producer_tenant_workspace_and_share(self):
        from manage_partner_share import invitation_url
        from http_api import ApiError
        url = ("https://app.powerbi.com/iqshare/accept?"
               "providerTenantId=producer&workspaceId=workspace&shareId=share")
        detail = {"id": "share", "properties": {"shareStatus": "Active", "invitationUrl": url}}
        self.assertEqual(invitation_url(detail, "producer", "workspace"), url)
        for invalid in (url.replace("workspaceId=workspace", "workspaceId=other"),
                        url.replace("app.powerbi.com", "unexpected.example"),
                        url.replace("shareId=share", "shareId=other")):
            with self.subTest(url=invalid), self.assertRaises(ApiError):
                invitation_url({**detail, "properties": {**detail["properties"],
                                                        "invitationUrl": invalid}},
                               "producer", "workspace")

    def test_documented_fabric_invitation_path_is_also_supported(self):
        from manage_partner_share import invitation_url
        url = "https://app.fabric.microsoft.com/share/invite/share"
        detail = {"id": "share", "properties": {"shareStatus": "Active", "invitationUrl": url}}
        self.assertEqual(invitation_url(detail, "producer", "workspace"), url)
