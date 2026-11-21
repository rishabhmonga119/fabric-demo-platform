from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from openpyxl import load_workbook
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from common import ROOT
from generate_excel import HEADERS, forecasts, workbook_bytes
from upload_sharepoint import assert_readable_xlsx, verify_uploaded_workbook
from data_model import VALID_COMBINATIONS, generate_model


class ForecastWorkbookTests(unittest.TestCase):
    def test_protected_office_container_is_rejected_before_upload(self):
        with self.assertRaisesRegex(RuntimeError, "protected/encrypted"):
            assert_readable_xlsx(bytes.fromhex("d0cf11e0a1b11ae1") + bytes(512),
                                 "generated.xlsx")

    def test_forecasts_have_unique_full_channel_grain_and_project_future_months(self):
        rows = forecasts()
        baseline = [row for row in rows if row[0].month <= 11]
        self.assertEqual(len(baseline), 11 * len(VALID_COMBINATIONS) * 4 * 4)
        self.assertEqual(len({row[:5] for row in baseline}), len(baseline))
        self.assertEqual(rows, forecasts())
        actuals = {row[:5]: row[5] for row in generate_model("dev")["fact_sales_monthly"]}
        january = next(row for row in rows if row[0] == date(2026, 1, 1))
        actual = actuals[january[:5]]
        self.assertGreaterEqual(january[5], actual * Decimal(".85") - Decimal(".01"))
        self.assertLessEqual(january[5], actual * Decimal("1.15") + Decimal(".01"))
        self.assertTrue(any(row[0] == date(2026, 12, 1) for row in rows))

    def test_standard_workbook_is_byte_stable_and_raw_retains_reject_and_duplicate(self):
        mappings = yaml.safe_load((ROOT / "config" / "mappings.yml").read_text())
        rows = forecasts()[:10]
        standard = workbook_bytes(rows, "standard", mappings)
        time.sleep(1.1)
        self.assertEqual(standard, workbook_bytes(rows, "standard", mappings))
        book = load_workbook(BytesIO(standard), read_only=True)
        self.assertEqual(tuple(book["Forecast"].values)[0], HEADERS)
        book.close()
        raw = load_workbook(BytesIO(workbook_bytes(rows, "wholesale", mappings)), read_only=True)
        values = list(raw.active.values)[4:]
        self.assertEqual(sum(row[1] == "SKU-XXX-999" for row in values), 1)
        self.assertEqual(sum(row == values[0] for row in values), 2)
        raw.close()

    def test_sharepoint_package_size_change_is_allowed_only_when_all_cells_match(self):
        mappings = yaml.safe_load((ROOT / "config" / "mappings.yml").read_text())
        rows = forecasts()[:2]
        content = workbook_bytes(rows, "standard", mappings)
        item = {"name": "forecast.xlsx", "size": len(content) + 100, "file": {},
                "@microsoft.graph.downloadUrl": "https://demo.sharepoint.com/download"}
        response = MagicMock()
        response.read.return_value = content
        with patch("upload_sharepoint.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = response
            verify_uploaded_workbook(item, content, "demo.sharepoint.com", "forecast.xlsx")
            request = opener.return_value.open.call_args.args[0]
            self.assertNotIn("Authorization", request.headers)
            changed = list(rows)
            first = list(changed[0])
            first[5] += 1
            changed[0] = tuple(first)
            response.read.return_value = workbook_bytes(changed, "standard", mappings)
            with self.assertRaisesRegex(RuntimeError, "cell values differ"):
                verify_uploaded_workbook(item, content, "demo.sharepoint.com", "forecast.xlsx")


if __name__ == "__main__":
    unittest.main()
