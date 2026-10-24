"""Download original CFTC COT API reports to OneDrive without using PostgreSQL.

Usage:
    python -m cot_ingest.download history --start-year 2025 --end-year 2025
    python -m cot_ingest.download history
    python -m cot_ingest.download weekly --lookback-days 56
    python -m cot_ingest.download history --start-year 2025 --end-year 2025 --refresh

Data is stored under D:\\OD\\OneDrive\\Fin\\data\\COT\\raw\\cftc_api,
in immutable snapshots with a SHA-256-validated manifest. No DB connection is opened.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import logging
import sys

from cot_ingest.archive import archive_root, ensure_archive
from cot_ingest.cli import (
    DATASETS, ORDER, api_session, check_dataset_selection, source_count, where_clause,
)

LOG = logging.getLogger("cot.download")


def download(
    mode: str,
    datasets: list[str],
    start_year: int | None = None,
    end_year: int | None = None,
    lookback_days: int = 56,
    page_size: int = 3000,
    refresh: bool = False,
) -> tuple[int, int]:
    """Return (number of complete dataset-windows, total downloaded/reused rows)."""
    if page_size < 1 or page_size > 10000:
        raise ValueError("--page-size must be between 1 and 10000")
    current = datetime.now(timezone.utc).date()
    if mode == "history":
        if start_year is not None and (start_year < 1900 or start_year > current.year):
            raise ValueError("Invalid start year")
        if end_year is not None and (end_year < 1900 or end_year > current.year):
            raise ValueError("Invalid end year")
        if start_year and end_year and start_year > end_year:
            raise ValueError("--start-year cannot exceed --end-year")
    elif mode == "weekly" and lookback_days < 7:
        raise ValueError("--lookback-days must be >= 7")

    finished, total_rows = 0, 0
    LOG.info("Original CFTC files destination: %s", archive_root())
    with api_session() as session:
        for dataset_id in datasets:
            if mode == "history":
                first_year = max(DATASETS[dataset_id][1], start_year or DATASETS[dataset_id][1])
                final_year = min(end_year or current.year, current.year)
                windows = [
                    (date(year, 1, 1), date(year + 1, 1, 1))
                    for year in range(first_year, final_year + 1)
                ]
            elif mode == "weekly":
                windows = [(current - timedelta(days=lookback_days),
                            current + timedelta(days=1))]
            else:
                raise ValueError(f"Unsupported download mode: {mode}")
            for start, stop in windows:
                archive = ensure_archive(
                    session, dataset_id, start, stop, mode, page_size,
                    get_count=source_count, make_where=where_clause, order=ORDER,
                    refresh_history=refresh,
                )
                finished += 1
                total_rows += archive.row_count
                LOG.info("%s %s to %s: %d rows archived at %s",
                         DATASETS[dataset_id][0], start, stop,
                         archive.row_count, archive.manifest_path)
    return finished, total_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download and validate original CFTC COT JSON to OneDrive. No DB access."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("history", "weekly"):
        p = sub.add_parser(name)
        p.add_argument("--datasets", default="all", help="all, Socrata IDs, or report codes")
        p.add_argument("--page-size", type=int, default=3000)
        if name == "history":
            p.add_argument("--start-year", type=int)
            p.add_argument("--end-year", type=int)
            p.add_argument("--refresh", action="store_true", help="Archive a new complete historical snapshot")
        else:
            p.add_argument("--lookback-days", type=int, default=56)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        count, rows = download(
            args.command,
            check_dataset_selection(args.datasets),
            start_year=getattr(args, "start_year", None),
            end_year=getattr(args, "end_year", None),
            lookback_days=getattr(args, "lookback_days", 56),
            page_size=args.page_size,
            refresh=getattr(args, "refresh", False),
        )
        print(f"Downloaded/validated {count} dataset-windows containing {rows} source rows.")
        print(f"Source archive: {archive_root()}")
        return 0
    except Exception as exc:
        LOG.exception("CFTC original-file download failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
