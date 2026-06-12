"""Tests for scripts/lib/segment_selection.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.message_importance import trim_message  # noqa: E402
from lib.segment_selection import (  # noqa: E402
    build_summary_bullets,
    coverage_ratio,
    select_per_segment,
    sqrt_budgets,
)


class TestSegmentSelection(unittest.TestCase):
    def test_trim_message(self) -> None:
        long = "word " * 200
        out = trim_message(long, max_chars=100)
        self.assertLessEqual(len(out), 104)
        self.assertTrue(out.endswith("..."))

    def test_sqrt_budgets_respects_total(self) -> None:
        budgets = sqrt_budgets([100, 25, 4], 30)
        self.assertEqual(len(budgets), 3)
        self.assertEqual(sum(budgets), 30)
        self.assertGreater(budgets[0], budgets[1])

    def test_per_segment_covers_multiple_segments(self) -> None:
        msgs = [f"topic A message {i} deploy prod ssl" for i in range(40)]
        msgs += [f"topic B message {i} schedule layers polishing" for i in range(40)]
        segments = [
            {"segment": 1, "start": 0, "count": 40, "preview": "topic A"},
            {"segment": 2, "start": 40, "count": 40, "preview": "topic B"},
        ]
        picked, enriched = select_per_segment(
            msgs,
            segments,
            max_messages=20,
            token_budget=8000,
            max_chars=200,
        )
        self.assertGreater(len(picked), 5)
        self.assertEqual(len(enriched), 2)
        self.assertTrue(enriched[0].get("bullets"))
        self.assertTrue(enriched[1].get("bullets"))

    def test_composite_summary_multi_segment(self) -> None:
        segments = [
            {"segment": 1, "preview": "alpha", "bullets": ["alpha detail"]},
            {"segment": 2, "preview": "beta", "bullets": ["beta detail"]},
        ]
        bullets = build_summary_bullets(
            segments,
            final_assistant="Final assistant tail about deploy",
            max_bullets=5,
        )
        self.assertGreaterEqual(len(bullets), 2)

    def test_coverage_ratio(self) -> None:
        self.assertEqual(coverage_ratio(13, 526), round(13 / 526, 4))


if __name__ == "__main__":
    unittest.main()
