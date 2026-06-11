"""Tests for scripts/lib/gitleaks_scan.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import gitleaks_scan as gl  # noqa: E402


class TestGitleaksScan(unittest.TestCase):
    def test_not_installed_returns_message(self) -> None:
        with mock.patch.object(gl, "gitleaks_available", return_value=False):
            findings, err = gl.scan_path_with_gitleaks(Path("/tmp"))
        self.assertEqual(findings, [])
        self.assertIn("not installed", err or "")

    def test_build_cmd_uses_dir_when_supported(self) -> None:
        with mock.patch.object(gl, "_gitleaks_supports_dir", return_value=True):
            cmd = gl._build_gitleaks_cmd(Path("/hub"), Path("/tmp/r.json"))
        self.assertEqual(cmd[1], "dir")

    def test_build_cmd_includes_config_when_present(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        cfg = repo / ".gitleaks.toml"
        self.assertTrue(cfg.is_file())
        with mock.patch.object(gl, "_gitleaks_supports_dir", return_value=True):
            cmd = gl._build_gitleaks_cmd(repo, Path("/tmp/r.json"), config=cfg)
        self.assertIn("--config", cmd)
        self.assertIn(str(cfg.resolve()), cmd)

    def test_resolve_config_finds_repo_toml(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        cfg = gl.resolve_gitleaks_config(repo)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.name, ".gitleaks.toml")

    def test_build_cmd_uses_detect_legacy(self) -> None:
        with mock.patch.object(gl, "_gitleaks_supports_dir", return_value=False):
            cmd = gl._build_gitleaks_cmd(Path("/hub"), Path("/tmp/r.json"))
        self.assertEqual(cmd[1], "detect")
        self.assertIn("--no-git", cmd)

    def test_findings_to_hits(self) -> None:
        hub = Path("/hub")
        hits = gl.findings_to_hits(
            [{"File": "/hub/feedback/wins.md", "StartLine": 3, "RuleID": "generic", "Match": "x"}],
            hub,
        )
        self.assertEqual(len(hits), 1)
        self.assertIn("gitleaks", hits[0][2])


if __name__ == "__main__":
    unittest.main()
