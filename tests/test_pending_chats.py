"""Tests for scripts/lib/pending_chats.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from helpers import minimal_hub

from lib import pending_chats as pc  # noqa: E402


class TestPendingChats(unittest.TestCase):
    def test_needs_distill_new_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            manifest = {"processed": [], "pending": []}
            self.assertTrue(pc.needs_distill("a", jsonl, manifest))

    def test_slugs_from_workspace_roots(self) -> None:
        slugs = pc.slugs_from_workspace_roots(["/tmp/workspaces/example-app"])
        self.assertIn("example-app", slugs)

    def test_filter_by_days(self) -> None:
        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        rows = [{"date": old, "mtime": 0}, {"date": "2099-01-01", "mtime": 1}]
        filtered = pc.filter_by_days(rows, 180)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["date"], "2099-01-01")

    def test_filter_by_slugs_exact_match(self) -> None:
        rows = [
            {
                "project": "example-app",
                "workspace": "Users-alice-Work-example-app",
            },
            {
                "project": "other-app",
                "workspace": "Users-alice-Work-other-app",
            },
        ]
        filtered = pc.filter_by_slugs(rows, {"xamp"})
        self.assertEqual(len(filtered), 0)
        filtered = pc.filter_by_slugs(rows, {"example-app"})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["project"], "example-app")

    def test_needs_distill_after_same_day_distill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            distilled = datetime.now().replace(hour=8).strftime("%Y-%m-%dT%H:%M:%S")
            manifest = {
                "processed": [{"id": "a", "distilled_at": distilled}],
                "pending": [],
            }
            import time

            time.sleep(0.05)
            jsonl.write_text("{}\n{}\n", encoding="utf-8")
            self.assertTrue(pc.needs_distill("a", jsonl, manifest))

    def test_scan_chat_stats_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            stats = pc.scan_chat_stats(hub, projects_root=hub)
            self.assertEqual(stats["status"], "ok")
            self.assertIn("total_chats", stats)
            self.assertIn("active_90d", stats)
            self.assertIn("pending_180d", stats)
            self.assertIn("message", stats)


if __name__ == "__main__":
    unittest.main()
