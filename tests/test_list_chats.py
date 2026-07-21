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
            # Present in the manifest, but distilled long before this transcript
            # was written — it still needs a pass. Counting only "absent from
            # the manifest" made this 0 while sync-memory reported it as work
            # to do, and a status line that disagrees with the tool stops being
            # read at all.
            self.assertEqual(pending, 1)

    def test_chat_counts_agrees_with_the_distill_gate(self) -> None:
        """One source of truth: the counter must use the gate distill uses."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub)
            root = Path(tmp) / "projects"
            uid = "fresh-chat-uuid"
            ws = root / "Users-me-Work-Foo" / "agent-transcripts" / uid
            ws.mkdir(parents=True)
            jsonl = ws / f"{uid}.jsonl"
            jsonl.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            from lib.chats_manifest import load_manifest
            from lib.pending_chats import needs_distill

            manifest_path = hub / "chats" / "manifest.json"
            _processed, pending, _total = lc.chat_counts(hub, root)
            manifest = load_manifest(manifest_path)
            self.assertEqual(pending, int(needs_distill(uid, jsonl, manifest)))


if __name__ == "__main__":
    unittest.main()
