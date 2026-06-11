"""Tests for metrics gap detection in memory-health."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import importlib.util

spec = importlib.util.spec_from_file_location("memory_health", SCRIPTS / "memory-health.py")
assert spec and spec.loader
mh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mh)


class TestMetricsGap(unittest.TestCase):
    def test_gap_when_sessions_without_boundary(self) -> None:
        rows = [
            {"ts": "2099-01-01T10:00:00", "event": "sessionStart", "status": "started"},
            {"ts": "2099-01-02T10:00:00", "event": "sessionStart", "status": "started"},
            {"ts": "2099-01-03T10:00:00", "event": "sessionStart", "status": "started"},
        ]
        data = mh.analyze_metrics(rows, days=7)
        self.assertTrue(data.get("metrics_gap"))


if __name__ == "__main__":
    unittest.main()
