"""Load already-downloaded weekly CFTC JSON files into PostgreSQL "COT".

Reads only OneDrive/COT/YYYY-MM-DD/<report>.json. Never calls the CFTC API.
Requires COT_DATABASE_URL and a pre-created cot schema.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path
import sys

from cot_ingest.cli import connect_db, convert_row, UPSERT_SQL
from cot_ingest.sources import DATASETS
from cot_ingest.weekly_files import iterate_weekly_files, validate_file

LOG = logging.getLogger("cot.import_files")
CODE_TO_ID = {code: identifier for identifier, (code, _) in DATASETS.items()}


def import_files(start: date, stop: date | None = None, *, mode: str = "history") -> tuple[int, int]:
    if mode not in {"history", "weekly"}:
        raise ValueError("Mode must be history or weekly")
    total_files = total_rows = 0
    with connect_db() as conn:
        lock = conn.execute("SELECT pg_try_advisory_lock(2026, 1024)").fetchone()[0]
        if not lock:
            raise RuntimeError("A COT loader is already running")
        try:
            run_id = conn.execute(
                "INSERT INTO cot.ingest_runs(mode) VALUES (%s) RETURNING run_id", (mode,)
            ).fetchone()[0]
            try:
                for when, code, file_path in iterate_weekly_files(start, stop):
                    dataset_id = CODE_TO_ID[code]
                    rows = validate_file(file_path, when, code)
                    args = [convert_row(dataset_id, row) for row in rows]
                    end = when + timedelta(days=1)
                    # Exactly one record per dataset/date/market. Duplicates are errors.
                    keys = {(values[1], values[2], values[3]) for values in args}
                    if len(keys) != len(args):
                        raise RuntimeError(f"Duplicate COT business keys in {file_path}")
                    # Atomic per-file transaction: either all of one report-date
                    # is inserted/upserted or none of that report is committed.
                    with conn.transaction():
                        conn.execute(
                            """INSERT INTO cot.ingest_windows
                               (run_id,dataset_id,from_date,to_date,expected_rows,
                                fetched_rows,status,source_file)
                               VALUES (%s,%s,%s,%s,%s,%s,'completed',%s)""",
                            (run_id,dataset_id,when,end,len(rows),len(rows),str(file_path)),
                        )
                        with conn.cursor() as cur:
                            cur.executemany(UPSERT_SQL, args)
                        db_rows = conn.execute(
                            """SELECT count(*) FROM cot.reports
                               WHERE dataset_id=%s AND report_date=%s""",
                            (dataset_id,when),
                        ).fetchone()[0]
                        if db_rows != len(rows):
                            raise RuntimeError(
                                f"COT count mismatch at {when} ({code}): "
                                f"file={len(rows)} db={db_rows}. No deletions performed."
                            )
                    total_files += 1
                    total_rows += len(rows)
                    if total_files % 50 == 0:
                        LOG.info("Imported %d weekly files / %d records", total_files, total_rows)
                conn.execute(
                    "UPDATE cot.ingest_runs SET status='completed',finished_at=now() WHERE run_id=%s",
                    (run_id,),
                )
            except Exception as exc:
                conn.execute(
                    """UPDATE cot.ingest_runs
                       SET status='failed',finished_at=now(),error_message=%s
                       WHERE run_id=%s""",
                    (str(exc)[:3000],run_id),
                )
                raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(2026, 1024)")
    return total_files, total_rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Import local position-date COT files into PostgreSQL")
    p.add_argument("--start-year", type=int, default=2019)
    p.add_argument("--recent-days", type=int, default=None,
                   help="If set, import only COT position dates in the last N days")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if a.start_year < 1986 or a.start_year > datetime.now(timezone.utc).year:
            raise ValueError("--start-year outside supported range")
        if a.recent_days is not None and a.recent_days < 7:
            raise ValueError("--recent-days must be at least 7")
        start = (datetime.now(timezone.utc).date() - timedelta(days=a.recent_days)
                 if a.recent_days is not None else date(a.start_year,1,1))
        files, rows = import_files(start, mode=("weekly" if a.recent_days else "history"))
        print(f"Loaded {files} COT files and {rows} records into PostgreSQL COT.")
        return 0
    except Exception as exc:
        LOG.exception("Failed to import COT weekly files: %s",exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
