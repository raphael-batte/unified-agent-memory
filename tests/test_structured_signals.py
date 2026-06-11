"""Tests for scripts/lib/structured_signals.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import structured_signals as ss  # noqa: E402
from lib.transcript_parse import parse_transcript  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "chat-with-todos.jsonl"


class TestStructuredSignals(unittest.TestCase):
    def test_open_todo_from_fixture(self) -> None:
        parsed = parse_transcript(FIXTURE)
        signal = ss.todo_pointer_from_parsed(parsed)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.source, "todo_state")
        self.assertIn("device QA", signal.text)

    def test_all_completed_returns_none(self) -> None:
        extract = {
            "all_todos_completed": True,
            "open_todos": [{"content": "Done task here ok", "status": "completed"}],
        }
        self.assertIsNone(ss.todo_pointer_from_extract(extract))

    def test_skips_short_todo(self) -> None:
        extract = {
            "all_todos_completed": False,
            "open_todos": [{"content": "short", "status": "in_progress"}],
        }
        self.assertIsNone(ss.todo_pointer_from_extract(extract))


if __name__ == "__main__":
    unittest.main()
