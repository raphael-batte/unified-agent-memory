"""Tests for scripts/lib/health_baseline.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import health_baseline as hb  # noqa: E402


class TestHealthBaseline(unittest.TestCase):
    def test_degradation_below_median(self) -> None:
        baseline = {"pointer_hit_median": 0.8, "pointer_hit_rates": [0.7, 0.8, 0.9]}
        window = {"pointer_extracted_rate": 0.5, "distilled": 5, "errors": 0}
        deg = hb.check_degradation(window, baseline)
        self.assertTrue(deg["degraded"])

    def test_no_degradation_with_few_samples(self) -> None:
        baseline = {"pointer_hit_median": 0.8, "pointer_hit_rates": [0.8]}
        window = {"pointer_extracted_rate": 0.5, "distilled": 5, "errors": 0}
        deg = hb.check_degradation(window, baseline)
        self.assertFalse(deg["degraded"])

    def test_record_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hb.record_snapshot(hub, pointer_hit_rate=0.6, distilled_count=3, error_count=0)
            loaded = hb.load_baseline(hub)
            self.assertEqual(len(loaded["samples"]), 1)
            self.assertEqual(loaded["pointer_hit_median"], 0.6)


if __name__ == "__main__":
    unittest.main()
