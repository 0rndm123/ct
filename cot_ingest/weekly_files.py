"""CFTC position-date file store: <COT_ROOT>/YYYY-MM-DD/<report_code>.json.

One JSON array per source dataset per CFTC report date. All source row fields are
preserved, but JSON files are reconstructed from paginated HTTP responses; they
are NOT byte-for-byte copies of original API response pages.

Existing archive (raw/cftc_api) can be imported non-destructively.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from cot_ingest.sources import DATASETS, DATE_FIELD

DEFAULT_ROOT = Path(r"D:\OD\OneDrive\Fin\data\COT")
CODES = {dataset_id: value[0] for dataset_id, value in DATASETS.items()}
KNOWN_CODES = set(CODES.values())


def root_path() -> Path:
    root = Path(os.environ.get("COT_RAW_DIR", str(DEFAULT_ROOT))).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"Invalid COT data folder: {root}")
    return root


def position_date(row: dict[str, Any]) -> date:
    raw = row.get(DATE_FIELD)
    if not isinstance(raw, str):
        raise ValueError(f"CFTC record has no {DATE_FIELD}: {row.get('id')!r}")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError(f"Bad CFTC date {raw!r}") from exc


def serialize_rows(rows: list[dict[str, Any]]) -> bytes:
    # Deterministic ordering => equal upstream data does not generate OneDrive churn.
    def key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (str(row.get("cftc_contract_market_code", "")),
                str(row.get("market_and_exchange_names", "")),
                str(row.get("id", "")))
    ordered = sorted(rows, key=key)
    return (json.dumps(ordered, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def validate_file(path: Path, date_expected: date, code: str) -> list[dict[str, Any]]:
    if code not in KNOWN_CODES:
        raise ValueError(f"Unknown COT file type {code}")
    rows = json.loads(path.read_bytes())
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise RuntimeError(f"Bad or empty COT JSON report: {path}")
    if any(position_date(row) != date_expected for row in rows):
        raise RuntimeError(f"Mixed report dates inside {path}")
    return rows


def save_rows(
    dataset_id: str,
    rows: Iterable[dict[str, Any]],
    start: date,
    stop: date,
    *,
    keep_existing: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Group one dataset-period into date folders, with atomic single-file writes.

    Return (report dates, changed files, record count). Do not delete other reports.
    """
    if dataset_id not in DATASETS:
        raise ValueError(f"Unknown CFTC dataset {dataset_id}")
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    count = 0
    for row in rows:
        d = position_date(row)
        if not (start <= d < stop):
            raise RuntimeError(f"Row {d} outside requested CFTC window {start}..{stop}")
        grouped[d].append(row)
        count += 1
    root = root_path()
    changed = 0
    code = CODES[dataset_id]
    for when, batch in sorted(grouped.items()):
        folder = root / when.isoformat()
        path = folder / f"{code}.json"
        new_bytes = serialize_rows(batch)
        if path.exists():
            old_rows = validate_file(path, when, code)
            if keep_existing:
                continue
            if serialize_rows(old_rows) == new_bytes:
                continue
        changed += 1
        if dry_run:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{code}-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(new_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return len(grouped), changed, count


def iterate_weekly_files(since: date | None = None, until: date | None = None):
    root = root_path()
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        try:
            when = date.fromisoformat(folder.name)
        except ValueError:
            continue
        if since and when < since:
            continue
        if until and when >= until:
            continue
        for path in sorted(folder.glob("*.json")):
            if path.stem not in KNOWN_CODES:
                continue
            yield when, path.stem, path


def verify_weekly_files(since: date | None = None) -> tuple[int, int, int]:
    """Validate every weekly report file independently, without accessing the CFTC API."""
    dates: set[date] = set()
    count, records = 0, 0
    for when, code, path in iterate_weekly_files(since):
        rows = validate_file(path, when, code)
        dates.add(when)
        count += 1
        records += len(rows)
    return len(dates), count, records


def migrate_old_archives(start_year: int = 2019, *, dry_run: bool = False) -> tuple[int, int]:
    """Copy existing old API-page snapshots into date folders WITHOUT deleting originals.

    Reuse the latest complete archive per (dataset, period). The user may delete the
    old hierarchy only AFTER independently verifying its migrated equivalents.
    """
    from cot_ingest.archive import SourceArchive, iter_archive_pages, validate_archive

    legacy_root = root_path() / "raw" / "cftc_api"
    if not legacy_root.is_dir():
        return 0, 0
    selected: dict[tuple[str, str, str], Path] = {}
    for manifest_path in legacy_root.glob("*/*/*/*/manifest.json"):
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        ds = metadata.get("dataset_id")
        start = metadata.get("from_date")
        stop = metadata.get("to_date_exclusive")
        if ds not in DATASETS or not start or not stop or not metadata.get("complete"):
            continue
        key = (ds, start, stop)
        if key not in selected or str(manifest_path) > str(selected[key]):
            selected[key] = manifest_path
    total_dates = changed_files = 0
    for (ds, start, stop), manifest_path in sorted(selected.items()):
        lo, hi = date.fromisoformat(start), date.fromisoformat(stop)
        if hi.year < start_year:
            continue
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        archive = SourceArchive(manifest_path.parent, metadata)
        validate_archive(archive)
        rows = [r for page in iter_archive_pages(archive) for r in page]
        rows = [r for r in rows if position_date(r).year >= start_year]
        if not rows:
            continue
        date_count, file_count, _ = save_rows(
            ds, rows, lo, hi, keep_existing=True, dry_run=dry_run
        )
        total_dates += date_count
        changed_files += file_count
    return total_dates, changed_files
