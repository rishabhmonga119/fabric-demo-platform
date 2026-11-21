import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bootstrap_databricks import explicit_privileges
from check_managed_storage import check_warehouse, result_rows
from databricks_sql import DatabricksSql


class ExplicitGrantTests(unittest.TestCase):
    def test_empty_sdk_grant_response_means_explicit_grants_are_missing(self):
        self.assertEqual(explicit_privileges({}, "admin@demo"), set())
        self.assertEqual(
            explicit_privileges({"privilege_assignments": []}, "admin@demo"), set()
        )

    def test_other_principals_do_not_satisfy_external_use_requirement(self):
        response = {"privilege_assignments": [
            {"principal": "other@demo", "privileges": ["EXTERNAL_USE_SCHEMA"]},
            {"principal": "ADMIN@DEMO", "privileges": ["USE_SCHEMA", "SELECT"]},
        ]}
        self.assertEqual(
            explicit_privileges(response, "admin@demo"), {"USE_SCHEMA", "SELECT"}
        )


class ManagedStorageCheckTests(unittest.TestCase):
    def test_warehouse_must_be_owned_serverless_and_cost_limited(self):
        warehouse = {
            "tags": {"custom_tags": [
                {"key": "demoOwner", "value": "demo-owner"},
                {"key": "createdBy", "value": "copilot-demo-build"},
            ]},
            "enable_serverless_compute": True, "auto_stop_mins": 15,
            "cluster_size": "2X-Small", "min_num_clusters": 1, "max_num_clusters": 1,
        }
        check_warehouse(warehouse, "demo-owner")
        for key, value in (("auto_stop_mins", 0), ("enable_serverless_compute", False),
                           ("max_num_clusters", 2), ("tags", {})):
            with self.subTest(key=key):
                with self.assertRaises(RuntimeError):
                    check_warehouse({**warehouse, key: value}, "demo-owner")

    def test_truncated_or_malformed_sql_results_are_rejected(self):
        response = {
            "manifest": {"format": "JSON_ARRAY", "schema": {"columns": [{"name": "count"}]}},
            "result": {"data_array": [["1"]]},
        }
        self.assertEqual(result_rows(response), (["count"], [["1"]]))
        with self.assertRaises(RuntimeError):
            result_rows({**response, "manifest": {**response["manifest"], "truncated": True}})
        with self.assertRaises(RuntimeError):
            result_rows({**response, "result": {"data_array": [["1", "unexpected"]]}})


class StatementExecutionTests(unittest.TestCase):
    def client(self):
        with patch("databricks_sql.cli", return_value="databricks"), \
             patch("databricks_sql.workspace_environment", return_value={}):
            return DatabricksSql({}, "owned-warehouse")

    def test_pending_statement_is_polled_until_actual_success(self):
        client = self.client()
        pending = {"statement_id": "statement-1", "status": {"state": "PENDING"}}
        succeeded = {"status": {"state": "SUCCEEDED"}, "result": {"data_array": [["7"]]}}
        with patch("databricks_sql.mutate", return_value=json.dumps(pending)), \
             patch.object(client, "read", return_value=succeeded) as read, \
             patch("databricks_sql.time.sleep"):
            self.assertEqual(client.execute("SELECT COUNT(*) FROM demo_dev.gold.dim_product"), succeeded)
            read.assert_called_once_with("api", "get", "/api/2.0/sql/statements/statement-1")

    def test_failed_statement_is_never_returned_as_successful_data(self):
        client = self.client()
        failed = {"status": {"state": "FAILED", "error": {"message": "permission denied"}}}
        with patch("databricks_sql.mutate", return_value=json.dumps(failed)):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                client.execute("SELECT * FROM demo_dev.gold.dim_product")


if __name__ == "__main__":
    unittest.main()
