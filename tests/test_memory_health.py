"""Tests for scripts/memory-health.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.distill_metrics import append_metric, read_metrics  # noqa: E402


def _load_memory_health():
    import importlib.util

    path = SCRIPTS / "memory-health.py"
    spec = importlib.util.spec_from_file_location("memory_health", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMemoryHealth(unittest.TestCase):
    def test_analyze_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            append_metric(
                hub,
                {
                    "event": "sessionEnd",
                    "status": "distilled",
                    "pointer_kind": "extracted",
                    "pointer_confidence": 0.9,
                    "duration_ms": 120,
                },
            )
            append_metric(
                hub,
                {"event": "sessionEnd", "status": "skipped", "reason": "debounced"},
            )
            mh = _load_memory_health()
            rows = read_metrics(hub)
            data = mh.analyze_metrics(rows, days=7)
            data = mh.enrich_with_baseline(hub, data, update_baseline=True)
            self.assertEqual(data["distilled"], 1)
            self.assertEqual(data["debounced"], 1)
            self.assertEqual(data["pointer_extracted_rate"], 1.0)
            self.assertEqual(data["baseline"]["samples"], 1)

    def test_session_pointer_hit_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            append_metric(
                hub,
                {
                    "event": "pointer_feedback",
                    "outcome": "unmeasured",
                    "disk_hit": True,
                    "workspace_slug": "app",
                },
            )
            append_metric(
                hub,
                {"event": "pointer_feedback", "outcome": "miss", "workspace_slug": "app2"},
            )
            mh = _load_memory_health()
            data = mh.analyze_metrics(read_metrics(hub), days=7)
            self.assertEqual(data["pointer_feedback_disk_hits"], 1)
            self.assertEqual(data["pointer_feedback_miss"], 1)
            self.assertEqual(data["pointer_session_hit_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
