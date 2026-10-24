"""PostgreSQL integration test: only runs when COT_TEST_DSN is configured.

The CI workflow creates an EPHEMERAL PostgreSQL database named COT. Do not use
a production database for these tests; they create roles and source fixtures.
"""
from __future__ import annotations

from datetime import date
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from setup_cot import bootstrap
from cot_ingest.import_weekly import import_files, verify_db
from cot_ingest.weekly_files import save_rows


@unittest.skipUnless(os.environ.get("COT_TEST_DSN"), "No test PostgreSQL configured")
class DatabaseIntegrationTests(unittest.TestCase):
    def test_idempotent_import_revisions_and_no_silent_deletes(self):
        admin_dsn = os.environ["COT_TEST_DSN"]
        with psycopg.connect(admin_dsn) as admin:
            server = admin.info.host
            port = admin.info.port
            admin_user = admin.info.user
            db = admin.info.dbname
        if db != "COT":
            self.fail(f"Refusing destructive integration test on unexpected database {db!r}")
        loader_secret = "CI_only_loader_password_12345!"
        app_secret = "CI_only_reader_password_23456!"
        bootstrap(server, port, admin_user, "CI_only_admin_password_12345!",
                  loader_secret, app_secret)

        with TemporaryDirectory() as td, patch.dict(os.environ, {"COT_RAW_DIR": td}):
            when = date(2025, 4, 1)
            def example(contract_code, amount):
                return {
                    "report_date_as_yyyy_mm_dd":"2025-04-01T00:00:00.000",
                    "cftc_contract_market_code":contract_code,
                    "market_and_exchange_names":"TEST CME",
                    "open_interest_all":amount,
                }

            initial = [example("000101", "1000"),example("000102", "2000")]
            save_rows("6dca-aqww", initial, when, date(2025,4,2))
            with psycopg.connect(
                host=server,port=port,dbname="COT",user="cot_loader",
                password=loader_secret,autocommit=True,
            ) as conn:
                self.assertEqual(import_files(when, date(2025,4,2),conn=conn),
                                 (1,0,2))
                self.assertEqual(import_files(when, date(2025,4,2),conn=conn),
                                 (0,1,0))
                revisions = conn.execute(
                    "SELECT count(*) FROM cot.report_revisions"
                ).fetchone()[0]
                self.assertEqual(revisions, 0)
                verify_db(conn)

                updated = [example("000101", "1500"),example("000102", "2000")]
                save_rows("6dca-aqww", updated, when, date(2025,4,2))
                self.assertEqual(import_files(when,date(2025,4,2),conn=conn),(1,0,2))
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM cot.report_revisions"
                ).fetchone()[0],1)

                # Source disappearance is rejected and DB state rolled back.
                save_rows("6dca-aqww",updated[:1],when,date(2025,4,2))
                with self.assertRaises(RuntimeError):
                    import_files(when,date(2025,4,2),conn=conn)
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM cot.reports WHERE report_date=%s",
                    (when,),
                ).fetchone()[0],2)
                self.assertEqual(conn.execute(
                    "SELECT row_count FROM cot.source_files WHERE report_date=%s",
                    (when,),
                ).fetchone()[0],2)

            with psycopg.connect(
                host=server,port=port,dbname="COT",user="cot_app",
                password=app_secret,autocommit=True,
            ) as reader:
                self.assertEqual(reader.execute(
                    "SELECT count(*) FROM cot.reports"
                ).fetchone()[0],2)
                with self.assertRaises(psycopg.Error):
                    reader.execute("DELETE FROM cot.reports")

if __name__ == "__main__":
    unittest.main()
