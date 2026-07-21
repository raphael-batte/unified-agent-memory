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
    def test_errors_degrade(self) -> None:
        deg = hb.check_degradation({"distilled": 5, "errors": 2}, {"samples": []})
        self.assertTrue(deg["degraded"])
        self.assertEqual(deg["degradation_reason"], "errors=2")

    def test_clean_window_is_not_degraded(self) -> None:
        deg = hb.check_degradation({"distilled": 5, "errors": 0}, {"samples": []})
        self.assertFalse(deg["degraded"])
        self.assertIsNone(deg["degradation_reason"])

    def test_retired_pointer_rate_does_not_degrade(self) -> None:
        """Regression: every apply reports deprecated_passthrough since `## Next
        step` was retired, so a 0% pointer rate is what health looks like. The
        old floor rule turned that into a permanent ⚠ and a notification per run."""
        window = {"pointer_extracted_rate": 0.0, "distilled": 40, "errors": 0}
        baseline = {"samples": [{"date": "2026-07-20", "distilled": 9, "errors": 0}]}
        self.assertFalse(hb.check_degradation(window, baseline)["degraded"])

    def test_record_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hb.record_snapshot(hub, distilled_count=3, error_count=0)
            loaded = hb.load_baseline(hub)
            self.assertEqual(len(loaded["samples"]), 1)
            self.assertEqual(loaded["samples"][0]["distilled"], 3)

    def test_snapshot_drops_retired_pointer_keys(self) -> None:
        """An existing baseline carries a pointer median — leaving it in place
        would invite someone to wire the retired rule back up."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hb.save_baseline(
                hub, {"samples": [], "pointer_hit_rates": [0.8], "pointer_hit_median": 0.8}
            )
            hb.record_snapshot(hub, distilled_count=1, error_count=0)
            loaded = hb.load_baseline(hub)
            self.assertNotIn("pointer_hit_median", loaded)
            self.assertNotIn("pointer_hit_rates", loaded)


if __name__ == "__main__":
    unittest.main()
