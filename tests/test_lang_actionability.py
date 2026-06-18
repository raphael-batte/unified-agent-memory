"""Tests for scripts/lib/lang_actionability.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import lang_actionability as la  # noqa: E402


class TestLangActionability(unittest.TestCase):
    def test_generic_only_rejects_ok(self) -> None:
        self.assertTrue(la.is_generic_only("ok"))
        self.assertFalse(la.is_pointer_actionable("ok", min_len=12))

    def test_davay_with_verb_passes(self) -> None:
        text = "\u0434\u0430\u0432\u0430\u0439 \u0437\u0430\u043f\u0443\u0441\u0442\u0438 \u0442\u0435\u0441\u0442\u044b \u043d\u0430 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0435"
        self.assertTrue(la.is_pointer_actionable(text, min_len=12))

    def test_substantive_tail_passes(self) -> None:
        self.assertTrue(
            la.is_pointer_actionable(
                "deploy the security patch to prod tonight",
                min_len=12,
            )
        )


if __name__ == "__main__":
    unittest.main()
