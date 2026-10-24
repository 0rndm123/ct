"""Offline tests: raw source archive must precede any database write."""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cot_ingest.archive import ensure_archive, iter_archive_pages, validate_archive


class FakeResponse:
    def __init__(self, payload, url):
        self.content = payload
        self.url = url

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params, timeout):
        self.calls += 1
        if not self.responses:
            raise AssertionError("Unexpected API download after file cache was populated")
        return FakeResponse(self.responses.pop(0), url + "?offset=" + str(params["$offset"]))


class ArchiveTests(unittest.TestCase):
    def test_raw_response_bytes_preserved_and_reusable(self):
        payload = b'[{"id":"1","open_interest_all":"300"},{"id":"2","open_interest_all":"600"}]'
        session = FakeSession([payload])
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"COT_RAW_DIR": temp}):
                a = ensure_archive(
                    session, "6dca-aqww", date(2025, 1, 1), date(2026, 1, 1),
                    "history", 3000, get_count=lambda *args: 2,
                    make_where=lambda *args: "date >= 2025-01-01",
                    order="report_date_as_yyyy_mm_dd ASC",
                )
                self.assertTrue(a.manifest_path.is_file())
                self.assertEqual((a.folder / "page_00000.json").read_bytes(), payload)
                self.assertEqual(a.manifest["pages"][0]["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(sum(len(x) for x in iter_archive_pages(a)), 2)
                b = ensure_archive(
                    session, "6dca-aqww", date(2025, 1, 1), date(2026, 1, 1),
                    "history", 3000, get_count=lambda *args: 999,
                    make_where=lambda *args: "ignored",
                    order="ignored",
                )
                self.assertEqual(b.folder, a.folder)
                self.assertEqual(session.calls, 1)

    def test_checksum_detects_tampering(self):
        payload = b'[{"id":"1"}]'
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"COT_RAW_DIR": temp}):
                a = ensure_archive(
                    FakeSession([payload]), "gpe5-46if",
                    date(2025, 1, 1), date(2026, 1, 1), "history", 1000,
                    get_count=lambda *args: 1, make_where=lambda *args: "x", order="y",
                )
                (a.folder / "page_00000.json").write_bytes(b"[]")
                with self.assertRaises(RuntimeError):
                    validate_archive(a)


if __name__ == "__main__":
    unittest.main()
