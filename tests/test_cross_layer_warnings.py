"""Tests for scripts/lib/cross_layer_warnings.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import cross_layer_warnings as clw  # noqa: E402


class TestCrossLayerWarnings(unittest.TestCase):
    def test_phrase_overlap_on_real_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "context").mkdir(parents=True)
            (hub / "feedback").mkdir()
            (hub / "context" / "conventions.md").write_text(
                "## Migrations\n\n"
                "Always require manual approval before any production database migration.\n",
                encoding="utf-8",
            )
            (hub / "feedback" / "fails.md").write_text(
                "## Migrations\n\n"
                "- skipped manual approval before production database migration on release\n",
                encoding="utf-8",
            )
            warnings = clw.collect_cross_layer_warnings(hub)
            self.assertTrue(any("phrase overlap" in w for w in warnings))

    def test_domain_tokens_alone_do_not_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "context").mkdir(parents=True)
            (hub / "feedback").mkdir()
            (hub / "context" / "conventions.md").write_text(
                "## Docker\n\nUse docker compose for local development stacks.\n"
                "## CI\n\nRun tests on every pull request before merge.\n"
                "## Deploy\n\nDeploy staging after green CI pipeline.\n"
                "## Branching\n\nFeature branches merge via squash commits.\n"
                "## Builds\n\nDocker images build on main branch pushes.\n",
                encoding="utf-8",
            )
            (hub / "feedback" / "fails.md").write_text(
                "## Docker\n\n- docker image failed to build on branch merge\n"
                "## CI\n\n- tests failed on pull request workflow run\n"
                "## Deploy\n\n- staging deploy blocked by failed docker build\n"
                "## Branching\n\n- merge conflict on feature branch integration\n"
                "## Builds\n\n- build pipeline timeout on main branch push\n",
                encoding="utf-8",
            )
            warnings = clw.collect_cross_layer_warnings(hub)
            overlap = [w for w in warnings if "phrase overlap" in w]
            self.assertEqual(overlap, [])

    def test_superseded_substring_still_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "context").mkdir(parents=True)
            (hub / "feedback").mkdir()
            bullet = "Never commit database passwords into tracked config files"
            (hub / "context" / "conventions.md").write_text(
                f"## Secrets\n\n{bullet} in repositories.\n",
                encoding="utf-8",
            )
            (hub / "feedback" / "fails.md").write_text(
                "## Secrets\n\n"
                f"- {bullet}\n"
                "  _superseded -> conventions.md Secrets_\n",
                encoding="utf-8",
            )
            warnings = clw.collect_cross_layer_warnings(hub)
            self.assertTrue(any("superseded fail" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
