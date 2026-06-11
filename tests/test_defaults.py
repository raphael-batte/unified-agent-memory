"""Tests for scripts/lib/defaults.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import defaults as d  # noqa: E402


class TestDefaults(unittest.TestCase):
    def test_load_thresholds_defaults(self) -> None:
        t = d.load_thresholds(None)
        self.assertEqual(t["max_distill_messages"], d.MAX_DISTILL_MESSAGES)

    def test_load_thresholds_override(self) -> None:
        t = d.load_thresholds({"thresholds": {"max_distill_messages": 50}})
        self.assertEqual(t["max_distill_messages"], 50)


if __name__ == "__main__":
    unittest.main()
