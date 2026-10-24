"""Fast local COT SQL integrity check, before requesting any passwords.

This checks repository version and a few structural invariants. It does not
replace actually applying the schema to a throwaway PostgreSQL test database.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql" / "01_schema.sql"
SETUP = ROOT / "sql" / "setup_existing_cot.sql"
VERSION = "-- COT_SCHEMA_VERSION: 20261024_2"


def validate_sql_files() -> None:
    for path in (SCHEMA, SETUP):
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Cannot read {path}: {exc}") from exc
        faults = []
        if not contents.startswith(VERSION + "\n"):
            faults.append("schema revision is old or unidentified")
        if contents.count("CREATE TABLE IF NOT EXISTS cot.source_files (") != 1:
            faults.append("source_files table definition missing or duplicated")
        if contents.count("CREATE TABLE IF NOT EXISTS cot.report_revisions (") != 1:
            faults.append("report_revisions definition missing or duplicated")
        if contents.count("CREATE OR REPLACE VIEW cot.v_numeric_metrics AS") != 1:
            faults.append("numeric metrics view missing or duplicated")
        if contents.count("COMMIT;") != 1 or not contents.rstrip().endswith("COMMIT;"):
            faults.append("schema transaction incomplete or trailing duplicate SQL")
        try:
            source = contents.split("CREATE TABLE IF NOT EXISTS cot.source_files (", 1)[1]
            source = source.split("CREATE INDEX IF NOT EXISTS idx_source_files_date", 1)[0]
            if not all(x in source for x in (
                "file_sha256 char(64) NOT NULL",
                "CHECK (length(file_sha256)",
                "row_count integer NOT NULL CHECK (row_count > 0)",
                "PRIMARY KEY (dataset_id, report_date)",
                ");",
            )):
                faults.append("source_files definition is truncated")
            if source.count("'") % 2:
                faults.append("source_files definition has an unterminated SQL string")
        except (IndexError, ValueError):
            faults.append("source_files DDL cannot be isolated")
        if faults:
            problems = "; ".join(faults)
            raise RuntimeError(
                f"STALE / INVALID COT SQL at {path}: {problems}. "
                "Please update the local repository before running the installer. "
                "From the CT root execute: git pull --ff-only origin main. "
                "Inspect 'git status --short' if the pull cannot proceed."
            )
        digest = hashlib.sha256(contents.encode("utf-8")).hexdigest()[:12]
        print(f"SQL preflight OK: {path.name} [{VERSION.split(': ', 1)[1]}], SHA256={digest}")


if __name__ == "__main__":
    try:
        validate_sql_files()
    except RuntimeError as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
