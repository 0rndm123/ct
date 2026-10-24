"""Fast offline unit tests. Run: python -m unittest discover -s tests -v"""
import unittest
from datetime import date
from decimal import Decimal

from cot_ingest.cli import (
    DATASETS, check_dataset_selection, convert_row, key_for,
    number_or_none, where_clause,
)


class CotIngestTests(unittest.TestCase):
    def test_all_seven_official_datasets(self):
        self.assertEqual(len(DATASETS), 7)
        self.assertIn("6dca-aqww", DATASETS)
        self.assertIn("yw9f-hn96", DATASETS)

    def test_year_window_uses_exclusive_upper_bound(self):
        value = where_clause(date(2025,1,1),date(2026,1,1))
        self.assertIn("2025-01-01T00:00:00", value)
        self.assertIn("< '2026-01-01T00:00:00'", value)

    def test_select_by_name_id_and_no_duplicates(self):
        self.assertEqual(check_dataset_selection("legacy_futures,6dca-aqww"), ["6dca-aqww"])
        self.assertEqual(check_dataset_selection("all"), list(DATASETS))
        with self.assertRaises(ValueError):
            check_dataset_selection("unknown_report")

    def test_preserve_contract_market_code_leading_zeroes(self):
        row = {
            "report_date_as_yyyy_mm_dd": "2026-10-20T00:00:00.000",
            "cftc_contract_market_code": " 099741 ",
            "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
        }
        self.assertEqual(key_for(row)[1], "099741")
        converted = convert_row("6dca-aqww", row)
        self.assertEqual(converted[2], "099741")
        self.assertEqual(len(converted[-1]), 64)

    def test_reject_missing_business_key(self):
        with self.assertRaises(ValueError):
            key_for({"report_date_as_yyyy_mm_dd":"2026-10-20"})

    def test_optional_numeric(self):
        self.assertEqual(number_or_none("140034.5"), Decimal("140034.5"))
        self.assertIsNone(number_or_none(None))
        with self.assertRaises(ValueError):
            number_or_none("n/a")


if __name__ == "__main__":
    unittest.main()
