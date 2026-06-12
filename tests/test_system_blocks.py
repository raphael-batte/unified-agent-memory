"""Tests for scripts/lib/system_blocks.py and transcript_parse integration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.system_blocks import strip_system_blocks  # noqa: E402
from lib.transcript_parse import parse_transcript  # noqa: E402


class TestSystemBlocks(unittest.TestCase):
    def test_strip_git_status_preserves_user_text(self) -> None:
        raw = (
            "Please fix canonical URLs in templates "
            "<git_status>modified: foo.php</git_status> "
            "before deploy."
        )
        out = strip_system_blocks(raw)
        self.assertNotIn("git_status", out)
        self.assertIn("canonical URLs", out)
        self.assertIn("before deploy", out)

    def test_strip_nested_agent_blocks(self) -> None:
        raw = (
            "<agent_transcripts>noise</agent_transcripts> "
            "new task: update sitemap robots"
        )
        out = strip_system_blocks(raw)
        self.assertEqual(out, "new task: update sitemap robots")

    def test_parse_transcript_strips_blocks_from_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            text = (
                "<user_query>deploy fix "
                "<git_status>M foo</git_status> "
                "on prod</user_query>"
            )
            path.write_text(
                json.dumps(
                    {
                        "role": "user",
                        "message": {"content": [{"type": "text", "text": text}]},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            parsed = parse_transcript(path, use_cache=False)
            self.assertEqual(len(parsed.user_messages), 1)
            self.assertNotIn("git_status", parsed.user_messages[0].text)
            self.assertIn("deploy fix", parsed.user_messages[0].text)


if __name__ == "__main__":
    unittest.main()
