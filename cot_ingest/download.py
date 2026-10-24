"""Download full CFTC COT datasets into ONE directory per CFTC report date.

Default range: 2019 to present. No PostgreSQL credentials are required.
All seven datasets share the same YYYY-MM-DD folder for any report date.

Usage:
    python -m cot_ingest.download history
    python -m cot_ingest.download history --start-year 2019 --end-year 2025
    python -m cot_ingest.download weekly
    python -m cot_ingest.download migrate
    python -m cot_ingest.download verify
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import logging
import sys
from typing import Any

from cot_ingest.sources import (
    BASE, DATASETS, ORDER, api_session, check_dataset_selection, source_count,
    where_clause,
)
from cot_ingest.weekly_files import (
    migrate_old_archives, root_path, save_rows, verify_weekly_files,
)

LOG = logging.getLogger("cot.download")


def download_window(session, dataset_id: str, start: date, stop: date,
                    page_size: int) -> tuple[int, int, int]:
    """Fetch a complete dataset/date-window and only then write weekly files."""
    expected = source_count(session, dataset_id, start, stop)
    fetched: list[dict[str, Any]] = []
    offset = 0
    while offset < expected:
        params = {
            "$where": where_clause(start, stop),
            "$order": ORDER,
            "$limit": min(page_size, expected - offset),
            "$offset": offset,
        }
        response = session.get(f"{BASE}/{dataset_id}.json", params=params, timeout=(15, 120))
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list) or not page or not all(isinstance(x, dict) for x in page):
            raise RuntimeError(f"Missing CFTC response for {dataset_id} {start} offset={offset}")
        if len(page) > params["$limit"]:
            raise RuntimeError(f"CFTC sent too many rows for {dataset_id} offset={offset}")
        offset += len(page)
        fetched.extend(page)
        LOG.info("%s %s: %d / %d rows", DATASETS[dataset_id][0], start.year, offset, expected)
    if len(fetched) != expected:
        raise RuntimeError(f"CFTC row-count mismatch {dataset_id} expected={expected}, got={len(fetched)}")
    # A changed count can signal that API pagination saw a moving dataset.
    final_count = source_count(session, dataset_id, start, stop)
    if final_count != expected:
        raise RuntimeError(f"CFTC dataset changed during download: {dataset_id} "
                           f"{start} initial={expected} final={final_count}. Retry.")
    return save_rows(dataset_id, fetched, start, stop)


def run_download(mode: str, datasets: list[str], *,
                 start_year: int = 2019, end_year: int | None = None,
                 lookback_days: int = 56, page_size: int = 3000) -> tuple[int, int, int]:
    now = datetime.now(timezone.utc).date()
    if not 2019 <= start_year <= now.year:
        raise ValueError(f"Start year must be between 2019 and {now.year}")
    if end_year is not None and not start_year <= end_year <= now.year:
        raise ValueError(f"End year must be between {start_year} and {now.year}")
    if not 1 <= page_size <= 10000:
        raise ValueError("page-size must be between 1 and 10000")
    if lookback_days < 7:
        raise ValueError("lookback-days must be at least 7")

    LOG.info("COT output: %s", root_path())
    windows = (
        [(date(year, 1, 1), date(year + 1, 1, 1))
         for year in range(start_year, (end_year or now.year) + 1)]
        if mode == "history" else
        [(now - timedelta(days=lookback_days), now + timedelta(days=1))]
    )
    dates, files, rows = 0, 0, 0
    with api_session() as session:
        for start, stop in windows:
            for dataset_id in datasets:
                try:
                    ndates, changed, total = download_window(
                        session, dataset_id, start, stop, page_size
                    )
                except Exception:
                    LOG.exception("FAILED dataset=%s window=%s..%s; no partial "
                                  "dataset-window was written", dataset_id, start, stop)
                    raise
                dates += ndates
                files += changed
                rows += total
                LOG.info("%s %s..%s: %d dates, %d new/updated files, %d rows",
                         DATASETS[dataset_id][0], start, stop, ndates, changed, total)
    return dates, files, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CFTC raw records organised as OneDrive/COT/YYYY-MM-DD/<report>.json"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    history = sub.add_parser("history", help="Download 2019 to today by CFTC report date")
    history.add_argument("--start-year", type=int, default=2019)
    history.add_argument("--end-year", type=int)
    history.add_argument("--datasets", default="all")
    history.add_argument("--page-size", type=int, default=3000)
    weekly = sub.add_parser("weekly", help="Refresh latest weeks after CFTC release")
    weekly.add_argument("--lookback-days", type=int, default=56)
    weekly.add_argument("--datasets", default="all")
    weekly.add_argument("--page-size", type=int, default=3000)
    checker = sub.add_parser("verify", help="Check all YYYY-MM-DD report files")
    checker.add_argument("--start-year", type=int, default=2019)
    migration = sub.add_parser("migrate", help="Reuse existing old-layout CFTC JSON archives")
    migration.add_argument("--start-year", type=int, default=2019)
    migration.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "verify":
            dates, files, rows = verify_weekly_files(date(args.start_year, 1, 1))
            print(f"Verified {dates} COT dates, {files} JSON files, {rows} records at {root_path()}")
            return 0 if files else 1
        if args.command == "migrate":
            dates, files = migrate_old_archives(args.start_year, dry_run=args.dry_run)
            print(f"Reused old archives: {dates} date groups examined, "
                  f"{files} new date files {'would be created' if args.dry_run else 'created'}.")
            print("Old source archive remains untouched; do not delete it without verification.")
            return 0
        dates, changed, rows = run_download(
            args.command, check_dataset_selection(args.datasets),
            start_year=getattr(args, "start_year", 2019),
            end_year=getattr(args, "end_year", None),
            lookback_days=getattr(args, "lookback_days", 56),
            page_size=args.page_size,
        )
        print(f"Processed {dates} report-date groups, saved {changed} changed JSON files; "
              f"validated {rows} CFTC records.")
        print(f"COT folder: {root_path()}")
        return 0
    except Exception as exc:
        LOG.exception("CFTC download failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
