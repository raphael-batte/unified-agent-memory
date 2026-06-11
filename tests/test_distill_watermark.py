"""Tests for scripts/lib/distill_watermark.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import distill_watermark as dw  # noqa: E402


def _user_line(text: str) -> str:
    return json.dumps(
        {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}
    )


class TestDistillWatermark(unittest.TestCase):
    def test_watermark_skips_small_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            lines = [_user_line(f"message {i} about deploy") for i in range(5)]
            jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            wm = dw.watermark_for_manifest(jsonl)
            entry = {
                "id": "a",
                "distilled_at": "2099-01-01T12:00:00",
                "watermark_user_count": wm["user_message_count"],
                "watermark_tail_hash": wm["tail_hash"],
            }
            self.assertFalse(dw.needs_distill_with_watermark(entry, jsonl))

    def test_watermark_needs_redistill_on_tail_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            jsonl.write_text(_user_line("one") + "\n" + _user_line("two") + "\n", encoding="utf-8")
            wm = dw.watermark_for_manifest(jsonl)
            entry = {
                "watermark_user_count": wm["user_message_count"],
                "watermark_tail_hash": "stalehash0000000",
            }
            self.assertTrue(dw.watermark_needs_redistill(entry, wm))

    def test_legacy_mtime_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            entry = {"distilled_at": "2000-01-01T00:00:00"}
            self.assertTrue(dw.needs_distill_with_watermark(entry, jsonl))


if __name__ == "__main__":
    unittest.main()
