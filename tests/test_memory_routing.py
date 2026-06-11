"""Tests for scripts/lib/memory_routing.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import memory_routing as mr  # noqa: E402


class TestMemoryRouting(unittest.TestCase):
    def test_known_slug_distill_only(self) -> None:
        layers = mr.session_read_layers(workspace_slug="app")
        self.assertEqual(layers, ["distill"])

    def test_unknown_slug_adds_global(self) -> None:
        layers = mr.session_read_layers(workspace_slug=None)
        self.assertEqual(layers, ["distill", "global-context"])

    def test_routing_summary(self) -> None:
        with __import__("tempfile").TemporaryDirectory() as tmp:
            hub = Path(tmp)
            summary = mr.routing_summary(hub)
            self.assertEqual(summary["memory_home"], str(hub))


if __name__ == "__main__":
    unittest.main()
