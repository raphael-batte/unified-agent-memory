"""Tests for scripts/lib/novelty.py"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
