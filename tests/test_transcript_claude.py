"""Tests for scripts/lib/transcript_claude.py — Claude Code jsonl adapter."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import transcript_claude as tc  # noqa: E402
from lib.transcript_cursor import TranscriptSchemaError  # noqa: E402
from lib.transcript_parse import clear_parse_cache, parse_transcript  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "claude-chat.jsonl"
CURSOR_FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample-chat.jsonl"
)


class TestRowDetection(unittest.TestCase):
    def test_conversation_row_detected(self) -> None:
        row = {"type": "user", "message": {"role": "user", "content": "hi"}}
        self.assertTrue(tc.is_claude_row(row))

    def test_cursor_row_rejected(self) -> None:
        """Cursor rows keep the role at the top level — must not be claimed."""
        row = {"role": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}
        self.assertFalse(tc.is_claude_row(row))

    def test_bookkeeping_rows_rejected(self) -> None:
        for kind in ("queue-operation", "attachment", "last-prompt", "summary"):
            self.assertFalse(tc.is_claude_row({"type": kind, "message": {"content": "x"}}))

    def test_non_dict_rejected(self) -> None:
        self.assertFalse(tc.is_claude_row(["user"]))
        self.assertFalse(tc.is_claude_row(None))


class TestNormalizeRows(unittest.TestCase):
    def test_string_content_becomes_text_block(self) -> None:
        rows = tc.normalize_rows(
            [{"type": "user", "message": {"role": "user", "content": "Deploy example-app"}}]
        )
        self.assertEqual(
            rows[0]["message"]["content"], [{"type": "text", "text": "Deploy example-app"}]
        )
        self.assertEqual(rows[0]["role"], "user")

    def test_sidechain_dropped(self) -> None:
        rows = tc.normalize_rows(
            [
                {
                    "type": "user",
                    "isSidechain": True,
                    "message": {"role": "user", "content": "subagent work"},
                }
            ]
        )
        self.assertEqual(rows, [])

    def test_tool_result_blocks_dropped_but_tool_use_kept(self) -> None:
        rows = tc.normalize_rows(
            [
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "tool_result", "content": "ok"}],
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                    },
                },
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message"]["content"][0]["type"], "tool_use")

    def test_metadata_carried_over(self) -> None:
        rows = tc.normalize_rows(
            [
                {
                    "type": "user",
                    "message": {"role": "user", "content": "hi"},
                    "timestamp": "2026-07-21T09:00:00.000Z",
                    "cwd": "/home/example-user/Work/example-app",
                    "gitBranch": "main",
                }
            ]
        )
        self.assertEqual(rows[0]["timestamp"], "2026-07-21T09:00:00.000Z")
        self.assertEqual(rows[0]["gitBranch"], "main")

    def test_empty_content_dropped(self) -> None:
        rows = tc.normalize_rows(
            [{"type": "user", "message": {"role": "user", "content": "   "}}]
        )
        self.assertEqual(rows, [])


class TestParseIntegration(unittest.TestCase):
    def setUp(self) -> None:
        clear_parse_cache()

    def test_adapter_is_claude(self) -> None:
        parsed = parse_transcript(FIXTURE)
        self.assertEqual(parsed.adapter, "claude")

    def test_user_texts_exclude_noise_and_sidechain(self) -> None:
        parsed = parse_transcript(FIXTURE)
        texts = parsed.user_texts()
        self.assertIn("Deploy example-app to staging with manual approval", texts)
        self.assertTrue(any("canonical URLs" in t for t in texts))
        self.assertFalse(any("Sidechain" in t for t in texts))
        self.assertFalse(any("deployed ok" in t for t in texts))

    def test_system_reminder_stripped(self) -> None:
        parsed = parse_transcript(FIXTURE)
        self.assertFalse(any("Ignore this injected block" in t for t in parsed.user_texts()))

    def test_assistant_blocks_and_tool_calls(self) -> None:
        parsed = parse_transcript(FIXTURE)
        self.assertTrue(any("Deploying example-app" in b.text for b in parsed.assistant_blocks))
        self.assertIn("Bash", [c.name for c in parsed.tool_calls])

    def test_todos_reconstructed(self) -> None:
        """TodoWrite reconstruction comes free from reusing the Cursor parser."""
        parsed = parse_transcript(FIXTURE)
        open_todos = [t.content for t in parsed.open_todos()]
        self.assertIn("Add canonical URLs", open_todos)
        self.assertNotIn("Verify staging deploy", open_todos)

    def test_stats_count_all_rows_read(self) -> None:
        parsed = parse_transcript(FIXTURE)
        line_count = len(
            [l for l in FIXTURE.read_text(encoding="utf-8").splitlines() if l.strip()]
        )
        self.assertEqual(parsed.stats.json_lines, line_count)

    def test_cursor_fixture_still_cursor(self) -> None:
        """Adding the Claude adapter must not steal Cursor transcripts."""
        parsed = parse_transcript(CURSOR_FIXTURE)
        self.assertEqual(parsed.adapter, "cursor")

    def test_extract_raw_user_texts(self) -> None:
        texts, stats = tc.extract_raw_user_texts(FIXTURE)
        self.assertGreaterEqual(len(texts), 2)
        self.assertGreater(stats.user_rows, 0)

    def test_extract_rejects_non_claude(self) -> None:
        with self.assertRaises(TranscriptSchemaError):
            tc.extract_raw_user_texts(CURSOR_FIXTURE)


class TestDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        tc.clear_transcript_cache()

    def test_flat_layout_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "-home-example-user-Work-example-app"
            project.mkdir(parents=True)
            (project / "claude-session-0001.jsonl").write_text(
                FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
            )
            index = tc.build_transcript_index(root)
            self.assertIn("claude-session-0001", index)
            found = tc.find_transcript("claude-session-0001", root)
            self.assertIsNotNone(found)
            self.assertEqual(found.stem, "claude-session-0001")

    def test_missing_root_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            self.assertEqual(tc.build_transcript_index(missing), {})
            self.assertIsNone(tc.find_transcript("any", missing))


if __name__ == "__main__":
    unittest.main()
