"""Import OneDrive COT/YYYY-MM-DD/<report>.json into the existing PostgreSQL COT.

- No network/API download.
- Atomic transaction per CFTC report family and position date.
- SHA256 cache skips unchanged files; changed CFTC rows are upserted and audited.
- No destructive deletion when a contract disappears in the upstream file.
- Persists file provenance and source row counts.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import logging
from pathlib import Path
import sys
from typing import Any

import psycopg

from cot_ingest.cli import connect_db, convert_row, UPSERT_SQL
from cot_ingest.sources import DATASETS
from cot_ingest.weekly_files import iterate_weekly_files, validate_file

LOG = logging.getLogger("cot.import_files")
CODE_TO_ID = {code: identifier for identifier, (code, _) in DATASETS.items()}


def existing_file(conn: psycopg.Connection, dataset_id: str, when: date):
    return conn.execute(
        """SELECT file_sha256,row_count FROM cot.source_files
           WHERE dataset_id=%s AND report_date=%s""",
        (dataset_id, when),
    ).fetchone()


def existing_db_count(conn: psycopg.Connection, dataset_id: str, when: date) -> int:
    return conn.execute(
        """SELECT count(*) FROM cot.reports
           WHERE dataset_id=%s AND report_date=%s""",
        (dataset_id, when),
    ).fetchone()[0]


def validate_keys(dataset_id: str, rows: list[dict[str, Any]]):
    """Map rows to typed values and reject duplicate source business keys."""
    args = []
    seen = set()
    for row in rows:
        values = convert_row(dataset_id, row)
        key = (values[1], values[2], values[3])
        if key in seen:
            raise ValueError(f"Duplicate CFTC business key: {dataset_id} {key}")
        seen.add(key)
        args.append(values)
    return args


def import_files(
    start: date,
    stop: date | None = None,
    *,
    mode: str = "history",
    conn: psycopg.Connection | None = None,
) -> tuple[int, int, int]:
    """Return (imported_files, skipped_files, source_rows_imported).

    A connection can be supplied by a secure interactive setup script without
    persisting database passwords in local files.
    """
    if mode not in ("history", "weekly"):
        raise ValueError("Invalid import mode")

    owns_connection = conn is None
    if owns_connection:
        conn = connect_db()
    assert conn is not None

    imported = skipped = total_rows = 0
    lock_acquired = False
    run_id = None
    try:
        database_name = conn.execute("SELECT current_database()").fetchone()[0]
        if database_name != "COT":
            raise RuntimeError(f"Expected PostgreSQL database COT; found {database_name!r}")
        lock_acquired = conn.execute(
            "SELECT pg_try_advisory_lock(2026, 1024)"
        ).fetchone()[0]
        if not lock_acquired:
            raise RuntimeError("Another COT ingestion process is running")

        run_id = conn.execute(
            "INSERT INTO cot.ingest_runs(mode) VALUES (%s) RETURNING run_id",
            (mode,),
        ).fetchone()[0]

        try:
            found_any = False
            for when, code, file_path in iterate_weekly_files(start, stop):
                found_any = True
                dataset_id = CODE_TO_ID[code]
                raw_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
                cached = existing_file(conn, dataset_id, when)
                if cached and cached[0] == raw_sha:
                    # Detect accidental removals from the target database.
                    in_db = existing_db_count(conn, dataset_id, when)
                    if cached[1] != in_db:
                        raise RuntimeError(
                            f"COT count changed unexpectedly {code} {when}: "
                            f"registry={cached[1]}, database={in_db}"
                        )
                    skipped += 1
                    continue

                rows = validate_file(file_path, when, code)
                args = validate_keys(dataset_id, rows)
                if not args:
                    raise ValueError(f"Empty file is not a valid report: {file_path}")

                # Do not update registration when any insert/upsert fails.
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.executemany(UPSERT_SQL, args)
                    in_db = existing_db_count(conn, dataset_id, when)
                    if in_db != len(rows):
                        raise RuntimeError(
                            f"Record-count mismatch: {code} {when}: "
                            f"file={len(rows)} vs database={in_db}. "
                            "The transaction was rolled back. No source rows were deleted."
                        )
                    conn.execute(
                        """INSERT INTO cot.source_files
                           (dataset_id,report_date,source_file,file_sha256,row_count)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (dataset_id,report_date) DO UPDATE SET
                             source_file=EXCLUDED.source_file,
                             file_sha256=EXCLUDED.file_sha256,
                             row_count=EXCLUDED.row_count,
                             last_loaded_at=now()""",
                        (dataset_id,when,str(file_path),raw_sha,len(rows)),
                    )
                    conn.execute(
                        """INSERT INTO cot.ingest_windows
                           (run_id,dataset_id,from_date,to_date,expected_rows,
                            fetched_rows,status,source_file)
                           VALUES (%s,%s,%s,%s,%s,%s,'completed',%s)""",
                        (run_id,dataset_id,when,when+timedelta(days=1),
                         len(rows),len(rows),str(file_path)),
                    )
                imported += 1
                total_rows += len(rows)
                LOG.info("Loaded %s %s: %s rows", when, code, len(rows))
            if not found_any:
                raise FileNotFoundError(
                    f"No COT JSON reports found for the selected period from {start}"
                )
            conn.execute(
                """UPDATE cot.ingest_runs
                   SET status='completed',finished_at=now()
                   WHERE run_id=%s""",
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
        if lock_acquired:
            conn.execute("SELECT pg_advisory_unlock(2026, 1024)")
        if owns_connection:
            conn.close()
    return imported, skipped, total_rows


def verify_db(conn: psycopg.Connection) -> None:
    print("PostgreSQL COT coverage (all dataset families):")
    for code, count, since, until in conn.execute(
        """SELECT d.report_code, count(r.report_date),
                  min(r.report_date), max(r.report_date)
           FROM cot.datasets d LEFT JOIN cot.reports r USING (dataset_id)
           GROUP BY d.report_code ORDER BY d.report_code"""
    ):
        print(f"  {code:30} {count:>10} rows  {since} to {until}")
    missing = conn.execute(
        """SELECT count(*) FROM cot.source_files s
           LEFT JOIN (
               SELECT dataset_id,report_date,count(*) AS n
               FROM cot.reports GROUP BY dataset_id,report_date
           ) r USING (dataset_id, report_date)
           WHERE r.n IS DISTINCT FROM s.row_count"""
    ).fetchone()[0]
    print(f"Tracked source files with DB count mismatch: {missing}")
    if missing:
        raise RuntimeError("Database count differs from one or more imported JSON files")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Import locally stored CFTC JSON into PostgreSQL database COT"
    )
    p.add_argument("--start-year", type=int, default=2019)
    p.add_argument("--recent-days", type=int,
                   help="Import only CFTC report dates from the latest N days")
    p.add_argument("--verify", action="store_true",
                   help="Only verify PostgreSQL coverage; do not write reports")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.verify:
            with connect_db() as conn:
                verify_db(conn)
            return 0
        today = datetime.now(timezone.utc).date()
        if not 1986 <= args.start_year <= today.year:
            raise ValueError("Invalid start year")
        if args.recent_days is not None and args.recent_days < 7:
            raise ValueError("--recent-days must be >= 7")
        start = today - timedelta(days=args.recent_days) if args.recent_days else date(args.start_year,1,1)
        imported, skipped, rows = import_files(
            start, mode="weekly" if args.recent_days else "history"
        )
        print(f"COT import complete: {imported} changed/new files, "
              f"{skipped} unchanged files skipped, {rows} source rows processed.")
        with connect_db() as conn:
            verify_db(conn)
        return 0
    except (psycopg.Error, ValueError, RuntimeError, OSError) as exc:
        LOG.error("COT import failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
