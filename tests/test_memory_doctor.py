"""Tests for scripts/memory-doctor.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import load_script_module, minimal_hub

md = load_script_module("memory_doctor", "memory-doctor.py")


class TestMemoryDoctor(unittest.TestCase):
    def test_run_doctor_minimal_hub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub)
            report = md.run_doctor(
                memory_home=hub,
                framework_root=None,
                strict_secrets=False,
            )
            self.assertTrue(report["memory_home_exists"])
            self.assertGreaterEqual(report["verify"]["passed"], 5)
            self.assertIn("path_resolution", report)
            self.assertNotIn("handoff_mode", report)

    def test_fix_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            fw = Path(tmp) / "fw"
            fw.mkdir()
            (fw / "INSTRUCTIONS.md").write_text("#", encoding="utf-8")
            (hub / "config.json").write_text("{}", encoding="utf-8")
            argv = [
                "memory-doctor.py",
                "--memory-home",
                str(hub),
                "--framework-root",
                str(fw),
                "--fix-dry-run",
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(md.main(), 0)

    def test_main_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub)
            argv = ["memory-doctor.py", "--memory-home", str(hub), "--json"]
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout"):
                self.assertEqual(md.main(), 0)


if __name__ == "__main__":
    unittest.main()
