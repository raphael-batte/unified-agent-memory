"""Tests for scripts/sync-memory.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, load_script_module, minimal_hub

sm = load_script_module("sync_memory", "sync-memory.py")


class TestSyncMemory(unittest.TestCase):
    def test_dry_run_report_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub, projects=1)
            report = sm.run_sync(
                memory_home=hub,
                framework_root=REPO_ROOT,
                days=180,
                dry_run=True,
                install_hooks=False,
            )
            self.assertTrue(report["dry_run"])
            self.assertIn("projects", report)
            self.assertEqual(report["distills"], 0)
            self.assertIn("distills_planned", report)
            self.assertIn("candidates", report)
            self.assertIn("message", report)

    def test_truncated_when_limit_smaller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub, projects=1)
            _, total, truncated = sm._resolve_pending(
                hub, projects_root=hub, days=180, limit=1
            )
            self.assertFalse(truncated)
            self.assertGreaterEqual(total, 0)

    def test_scan_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub, projects=1)
            stats = sm.run_scan(memory_home=hub, projects_root=hub)
            self.assertIn("pending_90d", stats)
            self.assertIn("pending_180d", stats)

    def test_plugin_bundle_skips_legacy_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub, projects=1)
            report = sm.run_sync(
                memory_home=hub,
                framework_root=REPO_ROOT,
                dry_run=False,
                install_hooks=True,
                projects_root=hub,
            )
            self.assertEqual(report["hooks"].get("reason"), "plugin_hooks_in_bundle")

    def test_sync_hub_config_strips_legacy_hub_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub, projects=1)
            sm.run_sync(
                memory_home=hub,
                framework_root=REPO_ROOT,
                dry_run=False,
                install_hooks=False,
                limit=0,
            )
            cfg = json.loads((hub / "config.json").read_text())
            for key in ("handoff_mode", "install_root", "dev_root"):
                self.assertNotIn(key, cfg)


if __name__ == "__main__":
    unittest.main()
