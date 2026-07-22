"""Unmerged staging must reach the health flag.

The hub reported a clean exit while merge-staging grew for weeks, because the
count was printed but never gated. Curated Decisions go stale exactly when this
backlog builds, so it is the signal worth failing on.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "memory_health", SCRIPTS / "memory-health.py"
)
memory_health = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(memory_health)


class TestStagingBacklogGate(unittest.TestCase):
    def _data(self, staging_files: int) -> dict:
        return {"healthy": True, "hub_disk": {"staging_files": staging_files}}

    def test_backlog_over_limit_marks_unhealthy(self) -> None:
        out = memory_health.apply_staging_backlog_gate(self._data(84))
        self.assertFalse(out["healthy"])
        self.assertIn("84", out["staging_backlog_reason"])

    def test_backlog_within_limit_stays_healthy(self) -> None:
        out = memory_health.apply_staging_backlog_gate(self._data(3))
        self.assertTrue(out["healthy"])
        self.assertNotIn("staging_backlog_reason", out)

    def test_empty_staging_is_healthy(self) -> None:
        out = memory_health.apply_staging_backlog_gate({"healthy": True})
        self.assertTrue(out["healthy"])
        self.assertEqual(out["staging_backlog"], 0)

    def test_limit_is_configurable(self) -> None:
        out = memory_health.apply_staging_backlog_gate(self._data(5), limit=4)
        self.assertFalse(out["healthy"])

    def test_gate_never_flips_unhealthy_back_to_healthy(self) -> None:
        data = {"healthy": False, "hub_disk": {"staging_files": 0}}
        self.assertFalse(memory_health.apply_staging_backlog_gate(data)["healthy"])


if __name__ == "__main__":
    unittest.main()
