"""Tests for scripts/verify-memory.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import load_script_module, minimal_hub

vm = load_script_module("verify_memory", "verify-memory.py")


class TestVerifyMemory(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_minimal_hub_passes(self) -> None:
        minimal_hub(self.hub, projects=2)
        results = [
            vm.check_global_context(self.hub),
            vm.check_conventions(self.hub),
            vm.check_feedback_fails(self.hub),
            vm.check_manifest(self.hub),
            vm.check_superseded_refs(self.hub),
            vm.check_no_secrets(self.hub),
        ]
        failed = [r for r in results if not r.ok]
        self.assertEqual(failed, [], msg=str(failed))

    def test_legacy_superseded_fails(self) -> None:
        minimal_hub(self.hub)
        fails = self.hub / "feedback" / "fails.md"
        fails.write_text(
            "- old\n  _superseded → conventions.md:22_\n",
            encoding="utf-8",
        )
        r = vm.check_superseded_refs(self.hub)
        self.assertFalse(r.ok)

    def test_valid_section_superseded(self) -> None:
        minimal_hub(self.hub)
        conv = self.hub / "context" / "conventions.md"
        conv.write_text("## Git\n\n- rule\n", encoding="utf-8")
        fails = self.hub / "feedback" / "fails.md"
        fails.write_text(
            "## T\n\n- x\n  _superseded → conventions.md § Git_\n",
            encoding="utf-8",
        )
        r = vm.check_superseded_refs(self.hub)
        self.assertTrue(r.ok)

    def test_run_checks_for_hub_tuple(self) -> None:
        minimal_hub(self.hub, projects=2)
        results, warnings = vm.run_checks_for_hub(self.hub)
        self.assertGreaterEqual(len(results), 7)
        self.assertIsInstance(warnings, list)

    def test_duplicate_lesson_warning(self) -> None:
        minimal_hub(self.hub)
        conv = self.hub / "context" / "conventions.md"
        conv.write_text("## Git\n\nshared lesson text for duplicate test\n", encoding="utf-8")
        fails = self.hub / "feedback" / "fails.md"
        fails.write_text(
            "## T\n\n- shared lesson text for duplicate test\n"
            "  _superseded → conventions.md § Git_\n",
            encoding="utf-8",
        )
        from lib.cross_layer_warnings import collect_cross_layer_warnings

        warnings = collect_cross_layer_warnings(self.hub)
        self.assertGreaterEqual(len(warnings), 1)

    def test_gitleaks_skipped_when_missing(self) -> None:
        minimal_hub(self.hub, projects=2)
        results, _ = vm.run_checks_for_hub(self.hub, gitleaks=True)
        names = [r.name for r in results]
        self.assertIn("gitleaks scan", names)
        g = [r for r in results if r.name == "gitleaks scan"][0]
        if not __import__("shutil").which("gitleaks"):
            self.assertTrue(g.ok)
            self.assertIn("skipped", g.detail)

    def test_main_exit_code(self) -> None:
        minimal_hub(self.hub, projects=2)
        argv = ["verify-memory.py", "--memory-home", str(self.hub), "-q"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout"):
            self.assertEqual(vm.main(), 0)


if __name__ == "__main__":
    unittest.main()
