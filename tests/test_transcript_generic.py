"""Tests for scripts/lib/transcript_generic.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import transcript_generic as tg  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "generic-chat.jsonl"


class TestTranscriptGeneric(unittest.TestCase):
    def test_extract_generic(self) -> None:
        texts, stats = tg.extract_raw_user_texts(FIXTURE)
        self.assertEqual(len(texts), 2)
        self.assertIn("Deploy example-app", texts[0])
        self.assertGreater(stats.user_rows, 0)


if __name__ == "__main__":
    unittest.main()
