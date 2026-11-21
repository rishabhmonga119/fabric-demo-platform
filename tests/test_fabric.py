import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fabric_preflight


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


if __name__ == "__main__":
    unittest.main()
