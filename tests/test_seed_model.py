from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "databricks" / "src"))
from data_model import TABLES, VALID_COMBINATIONS, business_checksums, generate_model


class SeedModelTests(unittest.TestCase):
    def test_numbers_and_grains_are_deterministic_and_stage_isolated(self):
        dev = generate_model("dev")
        prod = generate_model("prod")
        for name, definition in TABLES.items():
            with self.subTest(table=name):
                self.assertEqual([row[:-1] for row in dev[name]], [row[:-1] for row in prod[name]])
                self.assertEqual(business_checksums(dev[name]), business_checksums(prod[name]))
                self.assertTrue(all(row[-1] == "dev" for row in dev[name]))
                fields = [column[0] for column in definition["columns"]]
                indexes = [fields.index(key) for key in definition["keys"]]
                keys = [tuple(row[index] for index in indexes) for row in dev[name]]
                self.assertEqual(len(keys), len(set(keys)))
        sales = dev["fact_sales_monthly"]
        self.assertEqual(len(sales), 22 * len(VALID_COMBINATIONS) * 4 * 4)
        self.assertEqual({(row[1], row[2]) for row in sales}, set(VALID_COMBINATIONS))

    def test_partner_a_never_leaks_other_regions_and_delivery_percentage_is_bounded(self):
        rows = generate_model("dev")["fact_deliveries"]
        self.assertEqual({row[4] for row in rows if row[1] == "P-A"}, {"NORTH", "EAST"})
        self.assertTrue(all(85 <= row[6] <= 99 for row in rows))

    def test_business_fingerprint_detects_changes_outside_volume(self):
        rows = generate_model("dev")["fact_sales_monthly"]
        altered = list(rows)
        first = list(altered[0])
        first[7] += 1
        altered[0] = tuple(first)
        self.assertNotEqual(business_checksums(rows), business_checksums(altered))


if __name__ == "__main__":
    unittest.main()
