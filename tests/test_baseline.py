from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import common
from export_roles import canonical_roles
from build_manifest import manifest_file_sets
from http_api import ApiError


class BaselineSnapshotTests(unittest.TestCase):
    def test_cli_timeout_is_actionable_and_never_blindly_retried(self):
        error = common.subprocess.TimeoutExpired(["some-cli", "api", "post"], 180)
        with patch.object(common.subprocess, "run", side_effect=error) as command:
            with self.assertRaisesRegex(common.ContextError, "may have been accepted"):
                common.run(["some-cli", "api", "post"])
            command.assert_called_once()

    def test_role_ids_are_ignored_but_policies_and_members_are_preserved(self):
        roles = [{"id": "server-generated", "name": "DefaultReader",
                  "decisionRules": [{"effect": "Permit", "constraints": {"rows": ["NORTH"]}}],
                  "members": {"microsoftEntraMembers": [{"objectId": "south"}, {"objectId": "north"}]}}]
        original = deepcopy(roles)
        result = canonical_roles(roles)
        self.assertNotIn("id", result[0])
        self.assertEqual(result[0]["decisionRules"], roles[0]["decisionRules"])
        self.assertEqual(result[0]["members"]["microsoftEntraMembers"],
                         [{"objectId": "north"}, {"objectId": "south"}])
        self.assertEqual(roles, original)
        with self.assertRaises(common.ContextError):
            canonical_roles(roles * 2)

    def test_snapshots_never_overwrite_a_different_baseline_or_escape_repository(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(common, "ROOT", Path(directory).resolve()):
            path = Path("config") / "baseline.json"
            common.write_snapshot(path, {"roles": []}, dry_run=True)
            self.assertFalse((Path(directory) / path).exists())
            common.write_snapshot(path, {"roles": []})
            common.write_snapshot(path, {"roles": []})
            self.assertEqual(json.loads((Path(directory) / path).read_text()), {"roles": []})
            with self.assertRaises(common.ContextError):
                common.write_snapshot(path, {"roles": ["new"]})
            with self.assertRaises(common.ContextError):
                common.write_snapshot(Path("..") / "outside.json", {})

    def test_manifest_file_comparison_keeps_stage_path_and_seed_content_not_transient_etags(self):
        manifest = {"site_id": "site", "drive_id": "drive", "stages": {"dev": {"folder": "Forecasts/Dev", "files": {
            "standard/file.xlsx": {"item_id": "item", "etag": "old", "seed_sha256": "seed"}}}}}
        changed = deepcopy(manifest)
        changed["stages"]["dev"]["files"]["standard/file.xlsx"]["etag"] = "new"
        self.assertEqual(manifest_file_sets(manifest), manifest_file_sets(changed))
        changed["stages"]["dev"]["files"]["standard/file.xlsx"]["seed_sha256"] = "different"
        self.assertNotEqual(manifest_file_sets(manifest), manifest_file_sets(changed))

    def test_sql_mcp_csv_results_preserve_exact_decimals_and_reject_malformed_shapes(self):
        from types import SimpleNamespace
        from mcp.types import EmbeddedResource, TextResourceContents
        from fabric_sql import csv_rows

        def result(text):
            return SimpleNamespace(is_error=False, content=[EmbeddedResource(
                type="resource", resource=TextResourceContents(
                    uri="memory://baseline.csv", mime_type="text/csv", text=text))])

        self.assertEqual(csv_rows(result("row_count,volume\r\n1232,1121803.72\r\n")),
                         [{"row_count": "1232", "volume": "1121803.72"}])
        for invalid in ("rows,rows\n1,2\n", "rows,volume\n1232\n"):
            with self.subTest(csv=invalid), self.assertRaises(ApiError):
                csv_rows(result(invalid))
        with self.assertRaises(ApiError):
            csv_rows(SimpleNamespace(is_error=True, content=[]))

    def test_baseline_measure_check_uses_declarations_not_mentions_in_descriptions(self):
        from base64 import b64encode
        from verify_baseline import MEASURES, assert_baseline_measures
        source = "/// Forecast Accuracy % is not in this baseline.\ntable Sales\n" + \
            "\n".join(f"\tmeasure '{name}' = 1" for name in sorted(MEASURES))
        parts = [{"path": "definition/tables/Sales.tmdl",
                  "payload": b64encode(source.encode()).decode()}]
        assert_baseline_measures(parts)
        parts[0]["payload"] = b64encode(
            (source + "\n\tmeasure 'Forecast Accuracy %' = 0.9\n").encode()).decode()
        with self.assertRaises(common.ContextError):
            assert_baseline_measures(parts)

    def test_fallback_changes_only_add_measure_and_agent_guidance_preserving_baseline(self):
        from prepare_fallback import AGENT, GUIDANCE, MODEL, feature_sources
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / MODEL).parent.mkdir(parents=True)
            (root / AGENT).parent.mkdir(parents=True)
            baseline = ("table 'Sales vs Forecast'\n\tlineageTag: preserve-this\n"
                        "\tmeasure 'Actual hl' = 1\n\tmeasure 'Forecast hl' = 1\n"
                        "\t/// Month date.\n\tcolumn Month\n\t\tdataType: dateTime\n")
            original = {"aiInstructions": "Ontology only.\n", "opaque": {"preserve": True}}
            (root / MODEL).write_text(baseline, encoding="utf-8")
            (root / AGENT).write_text(json.dumps(original), encoding="utf-8")
            changes = feature_sources(root)
            self.assertEqual(set(changes), {MODEL, AGENT})
            self.assertIn("\tmeasure 'Forecast Accuracy %' =", changes[MODEL])
            self.assertLess(changes[MODEL].index("\tmeasure 'Forecast Accuracy %' ="),
                            changes[MODEL].index("\tcolumn Month"))
            self.assertIn("\tlineageTag: preserve-this", changes[MODEL])
            expected = deepcopy(original)
            expected["aiInstructions"] += GUIDANCE
            self.assertEqual(json.loads(changes[AGENT]), expected)
