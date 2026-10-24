"""Load all seven official CFTC COT datasets, preserving source JSON verbatim."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

import psycopg
import requests
from psycopg.types.json import Jsonb

from cot_ingest.archive import ensure_archive, iter_archive_pages
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOG = logging.getLogger("cot")
BASE = "https://publicreporting.cftc.gov/resource"
DATE_FIELD = "report_date_as_yyyy_mm_dd"
ORDER = "report_date_as_yyyy_mm_dd ASC, cftc_contract_market_code ASC, market_and_exchange_names ASC, id ASC"

# id -> (readable code, earliest year). No dataset is silently omitted.
DATASETS: dict[str, tuple[str, int]] = {
    "6dca-aqww": ("legacy_futures", 1986),
    "jun7-fc8e": ("legacy_combined", 1995),
    "72hh-3qpy": ("disaggregated_futures", 2006),
    "kh3c-gbw2": ("disaggregated_combined", 2006),
    "gpe5-46if": ("tff_futures", 2006),
    "yw9f-hn96": ("tff_combined", 2006),
    "4zgm-a668": ("supplemental_cit", 2006),
}

UPSERT_SQL = """
INSERT INTO cot.reports (
    dataset_id,report_date,cftc_contract_market_code,market_and_exchange_names,
    source_id,cftc_market_code,cftc_commodity_code,commodity_name,
    commodity_group_name,commodity_subgroup_name,contract_market_name,
    open_interest,payload,payload_sha256
) VALUES (
    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
)
ON CONFLICT (dataset_id,report_date,cftc_contract_market_code,market_and_exchange_names)
DO UPDATE SET
    source_id=EXCLUDED.source_id,
    cftc_market_code=EXCLUDED.cftc_market_code,
    cftc_commodity_code=EXCLUDED.cftc_commodity_code,
    commodity_name=EXCLUDED.commodity_name,
    commodity_group_name=EXCLUDED.commodity_group_name,
    commodity_subgroup_name=EXCLUDED.commodity_subgroup_name,
    contract_market_name=EXCLUDED.contract_market_name,
    open_interest=EXCLUDED.open_interest,
    payload=EXCLUDED.payload,
    payload_sha256=EXCLUDED.payload_sha256,
    last_checked_at=now()
"""

def api_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5, backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"], respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": "CT-COT-Postgres/0.1 (public CFTC research)", "Accept": "application/json"})
    return s

def where_clause(start: date, stop: date) -> str:
    """Upper bound is exclusive, so adjacent years never overlap."""
    return (
        f"{DATE_FIELD} >= '{start.isoformat()}T00:00:00'"
        f" AND {DATE_FIELD} < '{stop.isoformat()}T00:00:00'"
    )

def source_count(session: requests.Session, dataset_id: str, start: date, stop: date) -> int:
    r = session.get(
        f"{BASE}/{dataset_id}.json",
        params={"$select": "count(*) as total", "$where": where_clause(start, stop)},
        timeout=(15, 120),
    )
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or len(rows) != 1 or "total" not in rows[0]:
        raise RuntimeError(f"Unexpected CFTC count response for {dataset_id}: {str(rows)[:200]}")
    return int(rows[0]["total"])

def iter_source_pages(
    session: requests.Session, dataset_id: str,
    start: date, stop: date, expected: int, page_size: int,
) -> Iterator[list[dict[str, Any]]]:
    offset = 0
    while offset < expected:
        params = {
            "$where": where_clause(start, stop),
            "$order": ORDER,
            "$limit": min(page_size, expected - offset),
            "$offset": offset,
        }
        resp = session.get(f"{BASE}/{dataset_id}.json", params=params, timeout=(15, 120))
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows or not all(isinstance(x, dict) for x in rows):
            raise RuntimeError(f"Missing/invalid CFTC page: {dataset_id}, offset={offset}, expected={expected}")
        if len(rows) > params["$limit"]:
            raise RuntimeError(f"API returned too many rows: {dataset_id}, offset={offset}")
        offset += len(rows)
        yield rows
    if offset != expected:
        raise RuntimeError(f"Count mismatch: {dataset_id} expected={expected}, fetched={offset}")

def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None

def number_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid open interest: {value!r}") from exc

def key_for(row: dict[str, Any]) -> tuple[date, str, str]:
    value = clean_text(row.get(DATE_FIELD))
    if not value:
        raise ValueError("Missing report date in CFTC API row")
    try:
        report_date = date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"Invalid CFTC report date: {value!r}") from exc
    code = clean_text(row.get("cftc_contract_market_code"))
    market = clean_text(row.get("market_and_exchange_names"))
    if not code or not market:
        raise ValueError(f"Missing CFTC business-key attributes for {report_date}, id={row.get('id')!r}")
    return report_date, code, market

def convert_row(dataset_id: str, row: dict[str, Any]) -> tuple[Any, ...]:
    report_date, code, market = key_for(row)
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return (
        dataset_id,report_date,code,market,clean_text(row.get("id")),
        clean_text(row.get("cftc_market_code")),
        clean_text(row.get("cftc_commodity_code")),
        clean_text(row.get("commodity_name")),
        clean_text(row.get("commodity_group_name")),
        clean_text(row.get("commodity_subgroup_name")),
        clean_text(row.get("contract_market_name")),
        number_or_none(row.get("open_interest_all")),
        Jsonb(row), digest,
    )

def check_dataset_selection(spec: str) -> list[str]:
    if spec == "all":
        return list(DATASETS)
    requested = [x.strip() for x in spec.split(",") if x.strip()]
    by_code = {v[0]: k for k, v in DATASETS.items()}
    selected: list[str] = []
    for item in requested:
        dataset_id = item if item in DATASETS else by_code.get(item)
        if not dataset_id:
            raise ValueError(f"Unknown dataset {item!r}. Use list-datasets for names.")
        if dataset_id not in selected:
            selected.append(dataset_id)
    if not selected:
        raise ValueError("At least one dataset is required")
    return selected

def connect_db() -> psycopg.Connection:
    dsn = os.getenv("COT_DATABASE_URL")
    if not dsn:
        raise RuntimeError("COT_DATABASE_URL is required (database name must be COT)")
    conn = psycopg.connect(dsn, autocommit=True, connect_timeout=15)
    actual_db = conn.execute("SELECT current_database()").fetchone()[0]
    if actual_db != "COT":
        conn.close()
        raise RuntimeError(
            f"Refusing to ingest into database {actual_db!r}; expected exactly 'COT'."
        )
    return conn

def ingest_window(
    conn: psycopg.Connection, session: requests.Session,
    run_id: int, dataset_id: str, start: date, stop: date, page_size: int,
    mode: str, offline: bool = False, refresh_archive: bool = False,
) -> None:
    # Complete and checksum-verify all original CFTC JSON files BEFORE writing any report rows.
    archive = ensure_archive(
        session, dataset_id, start, stop, mode, page_size,
        get_count=source_count, make_where=where_clause, order=ORDER,
        offline=offline, refresh_history=refresh_archive,
    )
    expected = archive.row_count
    LOG.info("Validated original CFTC archive: %s", archive.manifest_path)
    LOG.info("%s %s to %s: %s source rows", DATASETS[dataset_id][0], start, stop, expected)
    with conn.transaction():
        conn.execute(
            """INSERT INTO cot.ingest_windows(run_id,dataset_id,from_date,to_date,expected_rows,archive_manifest)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (run_id, dataset_id, start, stop, expected, str(archive.manifest_path)),
        )
    fetched = 0
    seen: set[tuple[date, str, str]] = set()
    try:
        for page in iter_archive_pages(archive):
            args = []
            for row in page:
                key = key_for(row)
                if key in seen:
                    raise ValueError(
                        f"Duplicate CFTC business key {key} for dataset {dataset_id}. "
                        "Check source schema before choosing conflict semantics."
                    )
                seen.add(key)
                if not (start <= key[0] < stop):
                    raise RuntimeError(f"API yielded a record outside requested window: {key}")
                args.append(convert_row(dataset_id, row))
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.executemany(UPSERT_SQL, args)
                    cur.execute(
                        """UPDATE cot.ingest_windows
                           SET fetched_rows=fetched_rows + %s
                           WHERE run_id=%s AND dataset_id=%s AND from_date=%s AND to_date=%s""",
                        (len(args),run_id,dataset_id,start,stop),
                    )
            fetched += len(args)
            LOG.info("%s %s: %s / %s", dataset_id, start, fetched, expected)
        if fetched != expected:
            raise RuntimeError(f"Incomplete fetch for {dataset_id}: {fetched} vs {expected}")
        count = conn.execute(
            """SELECT count(*) FROM cot.reports
               WHERE dataset_id=%s AND report_date >= %s AND report_date < %s""",
            (dataset_id,start,stop),
        ).fetchone()[0]
        if count != expected:
            raise RuntimeError(
                f"DB count differs from CFTC for {dataset_id} {start}..{stop}: "
                f"db={count}, CFTC={expected}. Inspect duplicate keys/removals."
            )
        with conn.transaction():
            conn.execute(
                """UPDATE cot.ingest_windows SET status='completed'
                   WHERE run_id=%s AND dataset_id=%s AND from_date=%s AND to_date=%s""",
                (run_id,dataset_id,start,stop),
            )
    except Exception as exc:
        with conn.transaction():
            conn.execute(
                """UPDATE cot.ingest_windows SET status='failed',error_message=%s
                   WHERE run_id=%s AND dataset_id=%s AND from_date=%s AND to_date=%s""",
                (str(exc)[:3000],run_id,dataset_id,start,stop),
            )
        raise

def run_ingestion(mode: str, datasets: list[str], start_year: int | None, end_year: int | None,
                  lookback_days: int, page_size: int,
                  offline: bool = False, refresh_archive: bool = False) -> None:
    today = datetime.now(timezone.utc).date()
    if page_size < 1 or page_size > 10000:
        raise ValueError("page-size must be between 1 and 10000")
    if mode == "history" and start_year and end_year and start_year > end_year:
        raise ValueError("start-year cannot exceed end-year")
    with connect_db() as conn:
        # One process per COT database at a time. Lock is connection-scoped.
        locked = conn.execute("SELECT pg_try_advisory_lock(2026, 1024)").fetchone()[0]
        if not locked:
            raise RuntimeError("Another COT ingestion process already holds the advisory lock")
        try:
            run_id = conn.execute(
                "INSERT INTO cot.ingest_runs(mode) VALUES (%s) RETURNING run_id", (mode,)
            ).fetchone()[0]
            LOG.info("COT run_id=%s started", run_id)
            session = api_session()
            try:
                for ds in datasets:
                    if mode == "history":
                        initial = max(DATASETS[ds][1], start_year or DATASETS[ds][1])
                        last = min(end_year or today.year, today.year)
                        windows = [
                            (date(y, 1, 1), date(y + 1, 1, 1))
                            for y in range(initial, last + 1)
                        ]
                    else:
                        if lookback_days < 7:
                            raise ValueError("lookback-days must be >= 7")
                        windows = [(today - timedelta(days=lookback_days), today + timedelta(days=1))]
                    for start, stop in windows:
                        ingest_window(conn, session, run_id, ds, start, stop, page_size,
                                      mode, offline=offline, refresh_archive=refresh_archive)
                conn.execute(
                    "UPDATE cot.ingest_runs SET status='completed',finished_at=now() WHERE run_id=%s",
                    (run_id,),
                )
            except Exception as exc:
                conn.execute(
                    """UPDATE cot.ingest_runs
                       SET status='failed',finished_at=now(),error_message=%s WHERE run_id=%s""",
                    (str(exc)[:3000],run_id),
                )
                raise
            finally:
                session.close()
        finally:
            conn.execute("SELECT pg_advisory_unlock(2026, 1024)")

def verify() -> None:
    with connect_db() as conn:
        for dataset_id, code, count, earliest, latest in conn.execute(
            """SELECT d.dataset_id,d.report_code,count(r.report_date),
                      min(r.report_date),max(r.report_date)
               FROM cot.datasets d LEFT JOIN cot.reports r USING(dataset_id)
               GROUP BY d.dataset_id,d.report_code ORDER BY d.report_code"""
        ):
            print(f"{code:29} {count:>9} rows  {str(earliest):10} -> {str(latest):10}")
        issues = conn.execute(
            """SELECT count(*) FROM cot.ingest_windows WHERE status='failed'"""
        ).fetchone()[0]
        print(f"Failed windows retained for investigation: {issues}")
        print("Latest run:",conn.execute(
            "SELECT run_id,mode,status,started_at,finished_at FROM cot.ingest_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone())

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Official CFTC COT history -> PostgreSQL database COT")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-datasets")
    sub.add_parser("verify")
    for mode in ("history", "weekly"):
        p = sub.add_parser(mode)
        p.add_argument("--datasets", default="all", help="comma-separated codes/IDs, or all")
        p.add_argument("--page-size", type=int, default=3000)
        p.add_argument("--offline", action="store_true",
                       help="Read already archived original JSON instead of downloading")
        p.add_argument("--refresh-archive", action="store_true",
                       help="Download a new immutable snapshot even for historical years")
        if mode == "history":
            p.add_argument("--start-year", type=int)
            p.add_argument("--end-year", type=int)
        else:
            p.add_argument("--lookback-days", type=int, default=56)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        if args.command == "list-datasets":
            for ds, (name, first) in DATASETS.items():
                print(f"{name:29} {ds}  from {first}")
        elif args.command == "verify":
            verify()
        else:
            run_ingestion(args.command,check_dataset_selection(args.datasets),
                          getattr(args,"start_year",None),getattr(args,"end_year",None),
                          getattr(args,"lookback_days",56),args.page_size,
                          offline=args.offline,refresh_archive=args.refresh_archive)
        return 0
    except (requests.RequestException, psycopg.Error, ValueError, RuntimeError) as exc:
        LOG.error("COT ingestion failed: %s",exc)
        return 1

if __name__ == "__main__":
    sys.exit(main())
