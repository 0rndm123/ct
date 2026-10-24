"""First-time COT PostgreSQL setup AND JSON import, with no saved credentials.

Runs SQL idempotently against the EXISTING COT database, prompts for fresh
cot_loader/cot_app passwords, then loads all available 2019+ JSON files into
COT using cot_loader, without storing either password in a file.

Usage from repo root:
    python scripts/setup_and_load.py
    python scripts/setup_and_load.py --setup-only
    python scripts/setup_and_load.py --start-year 2025
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
from getpass import getpass
from pathlib import Path
import logging
import os
import sys

import psycopg

from setup_cot import bootstrap, secret_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cot_ingest.import_weekly import import_files, verify_db
from cot_ingest.weekly_files import verify_weekly_files, root_path, iterate_weekly_files, KNOWN_CODES

LOG = logging.getLogger("cot.first_load")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set up existing COT PostgreSQL database and import CFTC JSON reports"
    )
    parser.add_argument("--host", default=os.getenv("PGHOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PGPORT", "5432")))
    parser.add_argument("--admin-user", default=os.getenv("COT_ADMIN_USER", "postgres"))
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Import selected available files even if some years or report families are missing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        this_year = datetime.now(timezone.utc).year
        if not 1986 <= args.start_year <= this_year:
            raise ValueError("Start year outside supported range")
        first_date = date(args.start_year,1,1)
        if not args.setup_only:
            dates, files, rows = verify_weekly_files(first_date)
            if files == 0:
                raise FileNotFoundError(
                    f"No date-folder CFTC JSON files found at {root_path()} "
                    f"from {args.start_year}. Run scripts\\download_history.bat first."
                )
            years: dict[int,set[str]] = defaultdict(set)
            dates_by_year: dict[int,set[date]] = defaultdict(set)
            for when, code, _ in iterate_weekly_files(first_date):
                if when.year > this_year:
                    raise RuntimeError(f"Unexpected future COT position date: {when}")
                years[when.year].add(code)
                dates_by_year[when.year].add(when)
            missing_years = sorted(set(range(args.start_year,this_year+1)) - set(years))
            missing_types = {
                year: sorted(KNOWN_CODES - codes)
                for year,codes in years.items()
                if KNOWN_CODES - codes
            }
            if missing_years or missing_types:
                print(f"WARNING: Missing COT years: {missing_years}; "
                      f"missing report families by year: {missing_types}")
                if not args.allow_partial:
                    raise RuntimeError(
                        "Incomplete local COT coverage. Run scripts\\download_history.bat "
                        "or use --allow-partial for a controlled pilot."
                    )
            for year in sorted(dates_by_year):
                print(f"  {year}: {len(dates_by_year[year])} distinct COT dates, "
                      f"{len(years[year])}/7 report families")
            print(f"Found {dates} COT report dates, {files} source files, "
                  f"{rows} records from {args.start_year} onward.")

        print(f"Connecting as PostgreSQL admin {args.admin_user} to {args.host}:{args.port}/COT")
        admin_password = getpass("PostgreSQL administrator password: ")
        loader_password = secret_for("cot_loader")
        app_password = secret_for("cot_app")

        bootstrap(args.host,args.port,args.admin_user,
                  admin_password,loader_password,app_password)
        admin_password = ""
        print("Schema, tables and application permissions have been verified.")
        if args.setup_only:
            return 0

        # Freshly configured credentials are used only in memory; no pgpass
        # required for the first load.
        with psycopg.connect(
            host=args.host,port=args.port,dbname="COT",
            user="cot_loader",password=loader_password,
            autocommit=True,connect_timeout=15,
        ) as conn:
            imported, skipped, records = import_files(
                first_date,mode="history",conn=conn,
            )
            print(f"Imported {imported} changed/new JSON files and {records} rows. "
                  f"Skipped {skipped} already loaded, unchanged files.")
            verify_db(conn)

        print("DONE. Data is in PostgreSQL COT; app user is cot_app (SELECT only).")
        print("Save the application and loader passwords in your password manager.")
        return 0
    except (psycopg.Error, OSError, ValueError, RuntimeError) as exc:
        LOG.error("Setup/import failed: %s",exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
