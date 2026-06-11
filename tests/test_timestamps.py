"""Tests for scripts/lib/timestamps.py"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import timestamps as ts  # noqa: E402


class TestTimestamps(unittest.TestCase):
    def test_parse_legacy_date(self) -> None:
        parsed = ts.parse_distilled_at("2026-06-06")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.strftime("%Y-%m-%d"), "2026-06-06")

    def test_parse_iso(self) -> None:
        parsed = ts.parse_distilled_at("2026-06-06T14:30:00")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.hour, 14)

    def test_same_day_redistill_with_iso(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "chat.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            base = 1_700_000_000.0
            os.utime(jsonl, (base, base))
            distilled = datetime.fromtimestamp(base).strftime("%Y-%m-%dT%H:%M:%S")
            os.utime(jsonl, (base + 10, base + 10))
            self.assertTrue(ts.transcript_is_newer_than_distill(jsonl, distilled))

    def test_legacy_date_same_day_afternoon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "chat.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            self.assertTrue(ts.transcript_is_newer_than_distill(jsonl, "2020-01-01"))

    def test_staging_date_slug_from_iso(self) -> None:
        self.assertEqual(
            ts.staging_date_slug("2026-06-06T15:04:05"),
            "2026-06-06",
        )


if __name__ == "__main__":
    unittest.main()
