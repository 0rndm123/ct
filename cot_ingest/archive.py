"""Lossless local archive of official CFTC API response bodies before any DB write.

Each successful extraction is an immutable directory with JSON response pages and a
manifest containing API request URLs, SHA-256 hashes and row counts.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import shutil
import tempfile
import uuid
from typing import Callable, Iterator

import requests

DEFAULT_RAW_ROOT = r"D:\OD\OneDrive\Fin\data\COT"
API_BASE = "https://publicreporting.cftc.gov/resource"


@dataclass(frozen=True)
class SourceArchive:
    folder: Path
    manifest: dict

    @property
    def manifest_path(self) -> Path:
        return self.folder / "manifest.json"

    @property
    def row_count(self) -> int:
        return int(self.manifest["expected_rows"])


def archive_root() -> Path:
    """A fixed OneDrive default; override only deliberately via COT_RAW_DIR."""
    raw = os.environ.get("COT_RAW_DIR", DEFAULT_RAW_ROOT).strip()
    if not raw:
        raise RuntimeError("COT_RAW_DIR is empty")
    root = Path(raw).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"Raw COT directory is not a directory: {root}")
    return root / "raw" / "cftc_api"


def _period_parent(root: Path, dataset_id: str, mode: str, start: date, stop: date) -> Path:
    if mode == "history":
        # Historical requests are partitioned by calendar year.
        period = str(start.year)
    elif mode == "weekly":
        period = f"{start:%Y%m%d}_{stop:%Y%m%d}"
    else:
        raise ValueError(f"Unknown archive mode: {mode}")
    return root / dataset_id / mode / period


def find_archive(parent: Path, dataset_id: str, start: date, stop: date) -> SourceArchive | None:
    if not parent.is_dir():
        return None
    for manifest_file in sorted(parent.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            if (
                manifest.get("dataset_id") == dataset_id
                and manifest.get("from_date") == start.isoformat()
                and manifest.get("to_date_exclusive") == stop.isoformat()
                and manifest.get("complete") is True
            ):
                archive = SourceArchive(manifest_file.parent, manifest)
                validate_archive(archive)
                return archive
        except (OSError, ValueError, KeyError, TypeError):
            # Fail closed on corrupted archives rather than silently skipping and
            # treating a damaged local copy as a missing copy.
            raise RuntimeError(f"Invalid COT archive: {manifest_file}")
    return None


def iter_archive_pages(archive: SourceArchive) -> Iterator[list[dict]]:
    expected = archive.row_count
    seen = 0
    pages = archive.manifest["pages"]
    if not isinstance(pages, list):
        raise RuntimeError(f"Invalid archive pages: {archive.manifest_path}")
    for idx, page in enumerate(pages):
        filename = page["filename"]
        if filename != f"page_{idx:05d}.json":
            raise RuntimeError(f"Unexpected page filename {filename!r} in {archive.folder}")
        raw = (archive.folder / filename).read_bytes()
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != page["sha256"]:
            raise RuntimeError(f"Raw file SHA256 mismatch: {archive.folder / filename}")
        if len(raw) != page["bytes"]:
            raise RuntimeError(f"Raw file size mismatch: {archive.folder / filename}")
        rows = json.loads(raw)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise RuntimeError(f"Invalid CFTC JSON array in {archive.folder / filename}")
        if len(rows) != page["rows"]:
            raise RuntimeError(f"Row count mismatch: {archive.folder / filename}")
        seen += len(rows)
        yield rows
    if seen != expected:
        raise RuntimeError(f"Archive total mismatch for {archive.folder}: {seen} vs {expected}")


def validate_archive(archive: SourceArchive) -> None:
    """Read every saved source page and verify SHA-256/length before database work."""
    if archive.manifest.get("complete") is not True:
        raise RuntimeError(f"Incomplete COT archive: {archive.manifest_path}")
    for _ in iter_archive_pages(archive):
        pass


def ensure_archive(
    session: requests.Session,
    dataset_id: str,
    start: date,
    stop: date,
    mode: str,
    page_size: int,
    *,
    get_count: Callable[[requests.Session, str, date, date], int],
    make_where: Callable[[date, date], str],
    order: str,
    offline: bool = False,
    refresh_history: bool = False,
) -> SourceArchive:
    root = archive_root()
    parent = _period_parent(root, dataset_id, mode, start, stop)
    # Historical downloads are cached. Weekly runs always archive a fresh source
    # snapshot; offline recovery reuses the latest complete snapshot.
    if offline or (mode == "history" and not refresh_history):
        existing = find_archive(parent, dataset_id, start, stop)
        if existing:
            return existing
        if offline:
            raise RuntimeError(f"No validated local source archive for {dataset_id} {start}..{stop}")

    expected = get_count(session, dataset_id, start, stop)
    if expected < 0:
        raise RuntimeError(f"Invalid CFTC source count: {expected}")
    parent.mkdir(parents=True, exist_ok=True)
    staging_root = root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"cot-{dataset_id}-", dir=staging_root))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_dir = parent / f"{timestamp}-{uuid.uuid4().hex[:12]}"
    manifest: dict = {
        "format_version": 1,
        "source": "CFTC Public Reporting Environment / Socrata API",
        "dataset_id": dataset_id,
        "mode": mode,
        "from_date": start.isoformat(),
        "to_date_exclusive": stop.isoformat(),
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_rows": expected,
        "actual_rows": 0,
        "page_size": page_size,
        "pages": [],
        "complete": False,
    }
    offset = 0
    try:
        while offset < expected:
            request_params = {
                "$where": make_where(start, stop),
                "$order": order,
                "$limit": min(page_size, expected - offset),
                "$offset": offset,
            }
            response = session.get(
                f"{API_BASE}/{dataset_id}.json", params=request_params, timeout=(15, 120)
            )
            response.raise_for_status()
            original_json = response.content
            rows = json.loads(original_json)
            if (
                not isinstance(rows, list) or not rows
                or not all(isinstance(item, dict) for item in rows)
                or len(rows) > request_params["$limit"]
            ):
                raise RuntimeError(f"Invalid CFTC page for {dataset_id}, offset {offset}")
            filename = f"page_{len(manifest['pages']):05d}.json"
            with (temp_dir / filename).open("xb") as output:
                output.write(original_json)
                output.flush()
                os.fsync(output.fileno())
            manifest["pages"].append({
                "filename": filename,
                "offset": offset,
                "rows": len(rows),
                "bytes": len(original_json),
                "sha256": hashlib.sha256(original_json).hexdigest(),
                "request_url": response.url,
            })
            offset += len(rows)
        if offset != expected:
            raise RuntimeError(f"Partial CFTC archive {dataset_id}: fetched {offset} of {expected}")
        manifest["actual_rows"] = offset
        manifest["complete"] = True
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        archived = SourceArchive(temp_dir, manifest)
        validate_archive(archived)
        # Never replace existing historical/weekly snapshots.
        os.replace(temp_dir, final_dir)
        return SourceArchive(final_dir, manifest)
    except Exception:
        # Incomplete pages are not promoted into the original-file archive.
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
