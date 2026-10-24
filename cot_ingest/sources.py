"""CFTC official Socrata API source catalog and query helpers (no PostgreSQL dependency)."""
from __future__ import annotations

from datetime import date
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://publicreporting.cftc.gov/resource"
DATE_FIELD = "report_date_as_yyyy_mm_dd"
ORDER = "report_date_as_yyyy_mm_dd ASC, cftc_contract_market_code ASC, market_and_exchange_names ASC"

# Official public CFTC datasets: ID -> (report code, first year).
DATASETS: dict[str, tuple[str, int]] = {
    "6dca-aqww": ("legacy_futures", 1986),
    "jun7-fc8e": ("legacy_combined", 1995),
    "72hh-3qpy": ("disaggregated_futures", 2006),
    "kh3c-gbw2": ("disaggregated_combined", 2006),
    "gpe5-46if": ("tff_futures", 2006),
    "yw9f-hn96": ("tff_combined", 2006),
    "4zgm-a668": ("supplemental_cit", 2006),
}


def api_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": "CT-COT-Postgres/0.1 (public CFTC research)",
        "Accept": "application/json",
    })
    return s


def where_clause(start: date, stop: date) -> str:
    """The upper date bound is exclusive, so yearly windows never overlap."""
    return (
        f"{DATE_FIELD} >= '{start.isoformat()}T00:00:00'"
        f" AND {DATE_FIELD} < '{stop.isoformat()}T00:00:00'"
    )


def source_count(session: requests.Session, dataset_id: str, start: date, stop: date) -> int:
    resp = session.get(
        f"{BASE}/{dataset_id}.json",
        params={"$select": "count(*) as total", "$where": where_clause(start, stop)},
        timeout=(15, 120),
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or len(rows) != 1 or "total" not in rows[0]:
        raise RuntimeError(f"Unexpected CFTC count response for {dataset_id}: {str(rows)[:200]}")
    return int(rows[0]["total"])


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
