"""Tests for scripts/lib/pointer_metrics.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.distill_metrics import read_metrics  # noqa: E402
from lib.pointer_metrics import log_pointer_feedback  # noqa: E402


class TestPointerMetrics(unittest.TestCase):
    def test_log_pointer_feedback_appends_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            log_pointer_feedback(
                hub,
                {
                    "outcome": "followed",
                    "workspace_slug": "app",
                    "disk_hit": True,
                },
            )
            rows = read_metrics(hub)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event"], "pointer_feedback")
            self.assertEqual(rows[0]["outcome"], "followed")


if __name__ == "__main__":
    unittest.main()
