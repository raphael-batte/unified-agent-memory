"""Tests for scripts/lib/transcript_parse.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from lib import transcript_parse as tp  # noqa: E402


class TestTranscriptParse(unittest.TestCase):
    def setUp(self) -> None:
        tp.clear_parse_cache()

    def test_sample_chat_user_messages(self) -> None:
        parsed = tp.parse_transcript(FIXTURES / "sample-chat.jsonl")
        self.assertEqual(parsed.adapter, "cursor")
        texts = parsed.user_texts()
        self.assertGreaterEqual(len(texts), 2)
        self.assertTrue(any("deploy" in t.lower() for t in texts))

    def test_todo_reconstruction_merge_patch(self) -> None:
        parsed = tp.parse_transcript(FIXTURES / "chat-with-todos.jsonl")
        open_todos = parsed.open_todos()
        self.assertEqual(len(open_todos), 1)
        self.assertEqual(open_todos[0].content, "Run device QA")
        self.assertEqual(open_todos[0].status, "in_progress")
        self.assertFalse(parsed._all_todos_completed)

    def test_last_assistant_summary(self) -> None:
        parsed = tp.parse_transcript(FIXTURES / "chat-with-todos.jsonl")
        summary = parsed.last_assistant_summary()
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn("device QA", summary)

    def test_single_file_read_with_cache(self) -> None:
        path = FIXTURES / "sample-chat.jsonl"
        original = Path.read_text
        reads = 0

        def counting_read(self_path, *args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal reads
            if self_path.resolve() == path.resolve():
                reads += 1
            return original(self_path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", counting_read):
            tp.clear_parse_cache()
            tp.parse_transcript(path)
            tp.parse_transcript(path)
            from lib.forward_pointer import extract_forward_pointer_result

            extract_forward_pointer_result(
                {"user_messages": [], "source_path": str(path)}
            )
        self.assertEqual(reads, 1)

    def test_generic_fixture(self) -> None:
        parsed = tp.parse_transcript(FIXTURES / "generic-chat.jsonl")
        self.assertEqual(parsed.adapter, "generic")
        self.assertGreaterEqual(len(parsed.user_texts()), 1)


if __name__ == "__main__":
    unittest.main()
