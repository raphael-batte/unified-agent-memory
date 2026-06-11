"""Tests for scripts/lib/transcript.py unified adapter."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import transcript as tr  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CURSOR_FIX = REPO / "tests" / "fixtures" / "sample-chat.jsonl"
GENERIC_FIX = REPO / "tests" / "fixtures" / "generic-chat.jsonl"


class TestTranscriptRouter(unittest.TestCase):
    def test_cursor_adapter(self) -> None:
        texts, _stats, adapter = tr.extract_raw_user_texts(CURSOR_FIX)
        self.assertEqual(adapter, "cursor")
        self.assertGreaterEqual(len(texts), 1)

    def test_generic_adapter(self) -> None:
        texts, _stats, adapter = tr.extract_raw_user_texts(GENERIC_FIX)
        self.assertEqual(adapter, "generic")
        self.assertEqual(len(texts), 2)

    def test_find_in_hub_transcripts(self) -> None:
        uid = "hub-import-uuid"
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            path = hub / "transcripts" / f"{uid}.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(GENERIC_FIX.read_text(encoding="utf-8"), encoding="utf-8")
            found = tr.find_transcript(uid, hub / "missing-projects", memory_home=hub)
            self.assertEqual(found.resolve(), path.resolve())


if __name__ == "__main__":
    unittest.main()
