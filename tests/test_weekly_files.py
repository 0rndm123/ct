"""Offline tests for date-first COT structure (no API / DB required)."""
import json
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cot_ingest.weekly_files import (
    root_path, save_rows, validate_file, verify_weekly_files, iterate_weekly_files
)


def cot_row(report_date, contract):
    return {
        "id": str(contract),
        "report_date_as_yyyy_mm_dd": report_date + "T00:00:00.000",
        "cftc_contract_market_code": str(contract),
        "market_and_exchange_names": "Test exchange",
        "open_interest_all": "123",
    }


class WeeklyFolderTests(unittest.TestCase):
    def test_one_folder_per_report_date_not_download_date(self):
        rows = [
            cot_row("2026-10-20", 20),
            cot_row("2026-10-13", 13),
            cot_row("2026-10-20", 21),
        ]
        with TemporaryDirectory() as td, patch.dict(os.environ, {"COT_RAW_DIR": td}):
            dates, changed, records = save_rows(
                "6dca-aqww", rows, date(2026, 10, 1), date(2026, 11, 1)
            )
            self.assertEqual((dates, changed, records), (2, 2, 3))
            folders = sorted(p.name for p in Path(td).iterdir())
            self.assertEqual(folders, ["2026-10-13", "2026-10-20"])
            path = Path(td) / "2026-10-20" / "legacy_futures.json"
            self.assertTrue(path.is_file())
            self.assertEqual(len(validate_file(path, date(2026,10,20), "legacy_futures")), 2)

            _, changed_again, _ = save_rows(
                "6dca-aqww", list(reversed(rows)),
                date(2026, 10, 1), date(2026, 11, 1)
            )
            self.assertEqual(changed_again, 0)
            self.assertEqual(verify_weekly_files(), (2, 2, 3))

    def test_second_report_shares_same_week_directory(self):
        with TemporaryDirectory() as td, patch.dict(os.environ, {"COT_RAW_DIR": td}):
            r = [cot_row("2026-10-20", 1)]
            save_rows("6dca-aqww", r, date(2026,10,1), date(2026,11,1))
            save_rows("gpe5-46if", r, date(2026,10,1), date(2026,11,1))
            self.assertEqual(
                sorted(p.name for p in (Path(td) / "2026-10-20").iterdir()),
                ["legacy_futures.json", "tff_futures.json"]
            )

    def test_reject_mixed_or_wrong_dates_and_bad_files(self):
        with TemporaryDirectory() as td, patch.dict(os.environ, {"COT_RAW_DIR": td}):
            with self.assertRaises(RuntimeError):
                save_rows("6dca-aqww", [cot_row("2018-12-25", 1)],
                          date(2019,1,1), date(2020,1,1))
            save_rows("6dca-aqww", [cot_row("2026-10-20", 1)],
                      date(2026,1,1), date(2027,1,1))
            p = Path(td) / "2026-10-20" / "legacy_futures.json"
            p.write_text(json.dumps([cot_row("2026-10-13", 1)]), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                verify_weekly_files()


if __name__ == "__main__":
    unittest.main()
