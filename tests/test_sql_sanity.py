"""Guard against truncated COT schema SQL and duplicated trailing DDL."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SqlSchemaSanityTests(unittest.TestCase):
    def test_expected_single_definitions_and_clean_transaction(self):
        for relative in ("sql/01_schema.sql", "sql/setup_existing_cot.sql"):
            with self.subTest(relative=relative):
                sql = (ROOT / relative).read_text(encoding="utf-8")
                self.assertTrue(sql.rstrip().endswith("COMMIT;"))
                self.assertEqual(sql.count("COMMIT;"), 1)
                for name in (
                    "cot.datasets", "cot.reports", "cot.ingest_runs",
                    "cot.ingest_windows", "cot.source_files", "cot.report_revisions",
                ):
                    self.assertEqual(
                        sql.count("CREATE TABLE IF NOT EXISTS " + name + " ("),
                        1, f"Invalid definition for {name} in {relative}"
                    )
                self.assertEqual(sql.count("CREATE OR REPLACE FUNCTION cot.audit_report_revision()"), 1)
                self.assertEqual(sql.count("CREATE OR REPLACE VIEW cot.v_numeric_metrics AS"), 1)
                self.assertEqual(sql.count("CREATE OR REPLACE VIEW cot.v_report_coverage AS"), 1)
                self.assertIn("CHECK (length(file_sha256)", sql)
                self.assertIn("row_count integer NOT NULL CHECK (row_count > 0)", sql)
                self.assertNotIn("COMMIT;\n),", sql)
                self.assertIn("GRANT SELECT ON ALL TABLES IN SCHEMA cot TO cot_app;",sql)


if __name__ == "__main__":
    unittest.main()
