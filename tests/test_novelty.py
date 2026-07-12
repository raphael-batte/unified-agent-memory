"""Tests for scripts/lib/novelty.py"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import novelty as nv  # noqa: E402


class TestNovelty(unittest.TestCase):
    def test_filters_duplicate_against_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text(
                "## Decisions\n\n- Use docker for production deploy on main server\n\n",
                encoding="utf-8",
            )
            prior = nv.collect_prior_texts(path)
            items = [
                "Use docker for production deploy on main server",
                "New decision: add smoke tests for canonical URLs",
            ]
            out = nv.filter_novel_items(items, prior)
            self.assertEqual(len(out), 1)
            self.assertIn("smoke tests", out[0])

    def test_marker_agnostic_dedup_curated_beats_extracted(self) -> None:
        gap = (
            "set gap between package cards and banner "
            "Cannot choose a package question 32px instead of 16px"
        )
        bullets = [
            f"[curated] **gap:** {gap}",
            f"[extracted] {gap}",
            gap,
        ]
        out = nv.dedupe_decision_bullets(bullets)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("[curated]"))

    def test_triple_identical_extracted_collapses(self) -> None:
        gap = (
            "set gap between package cards and banner "
            "Cannot choose a package question 32px instead of 16px"
        )
        bullets = [f"[extracted] {gap}"] * 3
        out = nv.dedupe_decision_bullets(bullets)
        self.assertEqual(len(out), 1)

    def test_curated_order_preserved_when_dropping_extracted_dupes(self) -> None:
        bullets = [
            "[curated] **arch:** first curated policy stays in place",
            "[extracted] duplicate noise about carousel filter packages",
            "[curated] **deploy:** second curated policy stays in place",
            "[extracted] duplicate noise about carousel filter packages",
        ]
        out = nv.dedupe_decision_bullets(bullets)
        self.assertEqual(len(out), 3)
        self.assertTrue(out[0].startswith("[curated]"))
        self.assertIn("first curated", out[0])
        self.assertTrue(out[2].startswith("[curated]"))

    def test_is_novel_rejects_extracted_when_curated_same_content(self) -> None:
        body = "gap between package cards and banner should be 32px not 16px"
        prior = [nv.normalize_decision_content(f"[curated] **gap:** {body}")]
        self.assertFalse(nv.is_novel(body, prior))

    def test_junk_filter_drops_mcp_and_briefly_inform(self) -> None:
        self.assertTrue(
            nv.is_decision_junk(
                "[extracted] <mcp_meta_tools> You have access to MCP tools through GetMcpTools"
            )
        )
        self.assertFalse(
            nv.is_decision_junk("[extracted] folder is named home not landing page")
        )
        self.assertFalse(nv.is_decision_junk("Curated deploy policy"))
        self.assertTrue(
            nv.is_decision_junk(
                "[extracted] Briefly inform the user about the task result and perform"
            )
        )

    def test_fuzzy_dedup_off_by_default_gap_32_vs_24_not_merged(self) -> None:
        a = "[extracted] add gap 32px between package cards and help banner text"
        b = "[extracted] add gap 24px between package cards and help banner text"
        out = nv.dedupe_decision_bullets([a, b], fuzzy=False)
        self.assertEqual(len(out), 2)

    def test_fuzzy_dedup_on_can_merge_reordered_tokens(self) -> None:
        prev = os.environ.get("DECISION_FUZZY_DEDUP")
        os.environ["DECISION_FUZZY_DEDUP"] = "1"
        try:
            a = "[extracted] gap 32px carousel filter packages banner"
            b = "[extracted] carousel filter gap 32px packages banner"
            out = nv.dedupe_decision_bullets([a, b], fuzzy=True)
            self.assertEqual(len(out), 1)
        finally:
            if prev is None:
                os.environ.pop("DECISION_FUZZY_DEDUP", None)
            else:
                os.environ["DECISION_FUZZY_DEDUP"] = prev

    def test_fuzzy_dedup_on_gap_32_vs_24_stays_distinct(self) -> None:
        prev = os.environ.get("DECISION_FUZZY_DEDUP")
        os.environ["DECISION_FUZZY_DEDUP"] = "1"
        try:
            a = "[extracted] add gap 32px between package cards and help banner text"
            b = "[extracted] add gap 24px between package cards and help banner text"
            out = nv.dedupe_decision_bullets([a, b], fuzzy=True)
            self.assertEqual(len(out), 2)
        finally:
            if prev is None:
                os.environ.pop("DECISION_FUZZY_DEDUP", None)
            else:
                os.environ["DECISION_FUZZY_DEDUP"] = prev


if __name__ == "__main__":
    unittest.main()
