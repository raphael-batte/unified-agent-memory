"""Tests for scripts/memory-status.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import load_script_module, minimal_hub

ms = load_script_module("memory_status", "memory-status.py")


class TestMemoryStatusMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_count_projects(self) -> None:
        minimal_hub(self.hub, projects=3)
        self.assertEqual(
            ms.count_projects(self.hub / "context" / "GLOBAL_CONTEXT.md"),
            3,
        )

    def test_count_open_fail_bullets(self) -> None:
        minimal_hub(self.hub)
        fails = self.hub / "feedback" / "fails.md"
        self.assertEqual(ms.count_feedback_bullets(fails, "-"), 2)
        self.assertEqual(ms.count_superseded(fails), 1)
        self.assertEqual(ms.count_open_fail_bullets(fails), 1)

    def test_fmt_size(self) -> None:
        self.assertEqual(ms.fmt_size(500), "500 B")
        self.assertEqual(ms.fmt_size(2048), "2.0 KB")

    def test_collect_and_brief(self) -> None:
        minimal_hub(self.hub, projects=2)
        data = ms.collect(self.hub, None)
        self.assertEqual(data["projects"], 2)
        self.assertEqual(data["wins"], 1)
        self.assertEqual(data["fails"], 2)
        self.assertEqual(data["fails_open"], 1)
        self.assertEqual(data["fails_superseded"], 1)
        self.assertEqual(data["chats_processed"], 1)

    def test_main_exits_zero(self) -> None:
        minimal_hub(self.hub)
        argv = [
            "memory-status.py",
            "--memory-home",
            str(self.hub),
            "--json",
            "--no-verify",
        ]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout"):
            self.assertEqual(ms.main(), 0)


if __name__ == "__main__":
    unittest.main()
