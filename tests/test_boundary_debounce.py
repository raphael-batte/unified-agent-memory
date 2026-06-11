"""Tests for scripts/lib/boundary_debounce.py"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import boundary_debounce as bd  # noqa: E402


class TestBoundaryDebounce(unittest.TestCase):
    def test_debounce_within_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            bd.record_boundary_distill(hub, "chat-1")
            self.assertTrue(bd.should_skip_debounce(hub, "chat-1", debounce_seconds=30))

    def test_debounce_expires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            bd.record_boundary_distill(hub, "chat-1")
            time.sleep(0.05)
            self.assertFalse(bd.should_skip_debounce(hub, "chat-1", debounce_seconds=0))


if __name__ == "__main__":
    unittest.main()
