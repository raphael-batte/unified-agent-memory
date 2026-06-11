"""Tests for scripts/lib/transcript_cursor.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import transcript_cursor as tc  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "sample-chat.jsonl"
BAD = REPO / "tests" / "fixtures" / "bad-schema.jsonl"
RED_ONLY = REPO / "tests" / "fixtures" / "redacted-only.jsonl"


class TestTranscriptCursor(unittest.TestCase):
    def test_extract_sample(self) -> None:
        texts, stats = tc.extract_raw_user_texts(FIXTURE)
        self.assertGreaterEqual(len(texts), 2)
        self.assertGreater(stats.user_rows, 0)

    def test_bad_schema_raises(self) -> None:
        with self.assertRaises(tc.TranscriptSchemaError):
            tc.extract_raw_user_texts(BAD)

    def test_safe_path_component_neutralizes_traversal(self) -> None:
        self.assertEqual(tc.safe_path_component("..", fallback="x"), "x")
        self.assertEqual(tc.safe_path_component("../../etc/passwd"), "passwd")
        self.assertEqual(tc.safe_path_component("a/b/c"), "c")
        injected = tc.safe_path_component("foo$(touch evil)bar")
        self.assertNotRegex(injected, r"[^A-Za-z0-9._-]")
        self.assertEqual(tc.safe_path_component(""), "unknown")
        # legitimate slugs pass through unchanged
        self.assertEqual(tc.safe_path_component("irm-vision-demo"), "irm-vision-demo")

    def test_workspace_slug_is_safe(self) -> None:
        self.assertEqual(tc.workspace_slug("Users-me-Work-irm"), "irm")
        slug = tc.workspace_slug("Users-me-Work-../../../etc/cron")
        self.assertNotIn("/", slug)
        self.assertNotIn("..", slug)

    def test_redacted_only_raises(self) -> None:
        with self.assertRaises(tc.TranscriptSchemaError):
            tc.extract_raw_user_texts(RED_ONLY)

    def test_find_transcript_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uid = "cache-test-uuid"
            ws = root / "Users-me-Work-Foo" / "agent-transcripts" / uid
            ws.mkdir(parents=True)
            jsonl = ws / f"{uid}.jsonl"
            jsonl.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            tc.clear_transcript_cache()
            p1 = tc.find_transcript(uid, root)
            p2 = tc.find_transcript(uid, root)
            self.assertEqual(p1, p2)
            self.assertTrue(p1 and p1.is_file())

    def test_workspace_slug(self) -> None:
        self.assertEqual(tc.workspace_slug("Users-alice-Work-example-app"), "example-app")


if __name__ == "__main__":
    unittest.main()
