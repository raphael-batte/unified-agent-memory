"""Tests for scripts/list-chats.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, load_script_module, minimal_hub

lc = load_script_module("list_chats", "list-chats.py")
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample-chat.jsonl"


class TestListChats(unittest.TestCase):
    def test_chat_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub)
            root = Path(tmp) / "projects"
            uid = "list-chat-uuid"
            ws = root / "Users-me-Work-Foo" / "agent-transcripts" / uid
            ws.mkdir(parents=True)
            (ws / f"{uid}.jsonl").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

            manifest = json.loads((hub / "chats" / "manifest.json").read_text())
            manifest["processed"].append({"id": uid, "distilled_at": "2026-01-01"})
            (hub / "chats" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            processed, pending, total = lc.chat_counts(hub, root)
            self.assertEqual(total, 1)
            self.assertEqual(processed, 2)
            self.assertEqual(pending, 0)


if __name__ == "__main__":
    unittest.main()
