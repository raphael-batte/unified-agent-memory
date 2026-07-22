"""Curated hub content must survive a mechanical distill pass.

Regression cover for a real data loss: a distill on an already-curated project
file re-wrapped every section through a bullets-only round trip. Wrapped lines,
### sub-headings and prose summaries were dropped, and raw user quotes were
appended next to the curated bullets.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import project_merge as pm  # noqa: E402
from lib.markdown_sections import bullets, format_bullets  # noqa: E402

CURATED = """# app
_Last updated: 2026-01-01_

## Summary

Prose summary of the project, written by an agent rather than bulleted.

## Decisions

### Deployment

- **Deploy only with a backup**: releases go to `releases/test` first, and the
  CSS revision moves with them (`abc123`)
- **Never ship the mobile ad slot** — it regressed twice (`def456`)

## Preferences

## Open threads

- **[mobile-ads]** Port the remaining lazy monetization · _upd 2026-01-01_ · active

## Recent

- 2026-01-01: [earlier chat](abcdef12)
"""


def _extract() -> dict:
    return {
        "uuid": "9999-0000",
        "workspace_slug": "app",
        "first_query": "some new question",
        "user_messages": ["please just commit and deploy it already"],
        "user_message_count": 3,
        "strategy": "importance",
        "summary_bullets": ["raw distilled summary line"],
        "decision_candidates": [
            {"text": "please just commit and deploy it already, with a backup"}
        ],
    }


class TestBulletRoundTrip(unittest.TestCase):
    def test_wrapped_bullet_survives_round_trip(self) -> None:
        block = "- first line of a bullet\n  continued on the next line\n- second bullet"
        items = bullets(block)
        self.assertEqual(len(items), 2)
        self.assertIn("continued on the next line", items[0])
        self.assertEqual(format_bullets(items), block)

    def test_indented_sub_bullet_is_not_promoted(self) -> None:
        items = bullets("- parent bullet\n  - nested detail")
        self.assertEqual(len(items), 1)
        self.assertIn("nested detail", items[0])


class TestCuratedPreservation(unittest.TestCase):
    def _apply(self, tmp: str) -> str:
        path = Path(tmp) / "app.md"
        path.write_text(CURATED, encoding="utf-8")
        pm.apply_extract_to_project(path, _extract(), today="2026-02-02")
        return path.read_text(encoding="utf-8")

    def test_wrapped_lines_and_headings_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = self._apply(tmp)
        self.assertIn("### Deployment", out)
        self.assertIn("CSS revision moves with them", out)
        self.assertIn("· active", out)

    def test_prose_summary_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = self._apply(tmp)
        self.assertIn("Prose summary of the project", out)
        self.assertNotIn("raw distilled summary line", out)

    def test_raw_candidates_not_appended_to_curated_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = self._apply(tmp)
        self.assertNotIn("[extracted]", out)
        self.assertNotIn("commit and deploy it already", out)

    def test_recent_still_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = self._apply(tmp)
        self.assertIn("2026-02-02", out)

    def test_uncurated_file_still_gets_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fresh.md"
            path.write_text(
                "# fresh\n_Last updated: 2020-01-01_\n\n"
                "## Summary\n\n\n## Decisions\n\n\n"
                "## Preferences\n\n\n## Open threads\n\n\n## Recent\n\n",
                encoding="utf-8",
            )
            pm.apply_extract_to_project(path, _extract(), today="2026-02-02")
            out = path.read_text(encoding="utf-8")
        self.assertIn("[extracted]", out)


class TestHasCuratedDecisions(unittest.TestCase):
    def test_machine_markers_are_not_curation(self) -> None:
        self.assertFalse(
            pm.has_curated_decisions(
                ["[extracted] raw", "[bootstrap] raw", "[auto] raw", "  "]
            )
        )

    def test_any_plain_bullet_counts(self) -> None:
        self.assertTrue(pm.has_curated_decisions(["[extracted] raw", "**Real:** rule"]))


class TestApplyGuardCuratedCount(unittest.TestCase):
    """The guard must not mistake raw candidates for curated content."""

    def _count(self, decisions: str) -> int:
        from lib.apply_guard import curated_decision_count

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.md"
            path.write_text(f"# p\n\n## Decisions\n\n{decisions}\n", encoding="utf-8")
            return curated_decision_count(path)

    def test_machine_markers_do_not_count(self) -> None:
        self.assertEqual(
            self._count("- [extracted] raw\n- [bootstrap] raw\n- [auto] raw"), 0
        )

    def test_curated_bullets_count(self) -> None:
        self.assertEqual(self._count("- [extracted] raw\n- **Real:** a rule"), 1)

    def test_wrapped_curated_bullet_counts_once(self) -> None:
        self.assertEqual(self._count("- **Real:** a rule\n  wrapped tail"), 1)


if __name__ == "__main__":
    unittest.main()
