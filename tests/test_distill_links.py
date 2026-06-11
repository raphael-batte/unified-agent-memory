"""Tests for scripts/lib/distill_links.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import distill_links as dl  # noqa: E402


class TestDistillLinks(unittest.TestCase):
    def test_chat_link_when_source_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "full-uuid-here.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            extract = {
                "uuid": "full-uuid-here",
                "first_query": "Fix deploy pipeline",
                "source_path": str(jsonl),
                "user_message_count": 3,
                "strategy": "tail",
                "keywords_hit": [],
            }
            enriched = dl.enrich_extract(extract)
            self.assertTrue(enriched["transcript_available"])
            link = dl.format_chat_markdown_link(enriched)
            self.assertIn("[Fix deploy pipeline]", link or "")
            self.assertIn("(full-uuid-here)", link or "")

    def test_no_link_when_missing(self) -> None:
        extract = {
            "uuid": "gone-uuid",
            "first_query": "Old chat",
            "transcript_available": False,
            "user_message_count": 1,
            "strategy": "tail",
            "keywords_hit": [],
        }
        self.assertIsNone(dl.format_chat_markdown_link(extract))
        bullet = dl.recent_bullet(extract, "2026-06-06")
        self.assertIn("archived", bullet)

    def test_recent_bullet_with_link(self) -> None:
        extract = {
            "uuid": "abc-def",
            "first_query": "Hello",
            "transcript_available": True,
            "user_message_count": 2,
            "strategy": "auto",
            "keywords_hit": ["deploy"],
        }
        bullet = dl.recent_bullet(extract, "2026-06-06")
        self.assertIn("[Hello](abc-def)", bullet)


if __name__ == "__main__":
    unittest.main()
