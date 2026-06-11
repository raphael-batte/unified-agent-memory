"""Tests for scripts/lib/transcript_stats.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import transcript_stats as ts  # noqa: E402


def _user_line(text: str) -> str:
    return json.dumps(
        {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}
    )


class TestTranscriptStats(unittest.TestCase):
    def test_count_and_tail_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "chat.jsonl"
            jsonl.write_text(
                "\n".join(
                    [
                        _user_line("first message about deploy"),
                        _user_line("second message"),
                        _user_line("third tail message"),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(ts.count_usable_user_messages(jsonl), 3)
            h1 = ts.tail_content_hash(jsonl)
            self.assertTrue(h1)
            jsonl.write_text(
                jsonl.read_text(encoding="utf-8")
                + _user_line("fourth changed tail")
                + "\n",
                encoding="utf-8",
            )
            h2 = ts.tail_content_hash(jsonl)
            self.assertNotEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
