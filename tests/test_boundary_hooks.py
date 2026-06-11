"""Tests for scripts/lib/boundary_hooks.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import boundary_hooks as bh  # noqa: E402


class TestChatId(unittest.TestCase):
    def test_from_transcript_path(self) -> None:
        payload = {"transcript_path": "/tmp/uuid-here/uuid-here.jsonl"}
        self.assertEqual(bh.chat_id_from_payload(payload), "uuid-here")


class TestDistillModuleCache(unittest.TestCase):
    def test_load_distill_modules_cached(self) -> None:
        bh._DISTILL_MODULES_CACHE = None
        first = bh._load_distill_modules()
        second = bh._load_distill_modules()
        self.assertIs(first[0], second[0])
        self.assertIs(first[1], second[1])
        bh._DISTILL_MODULES_CACHE = None


class TestSkipDistill(unittest.TestCase):
    def test_skip_when_manifest_newer_than_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats").mkdir()
            chat_id = "abc-123"
            manifest = {
                "processed": [
                    {
                        "id": chat_id,
                        "distilled_at": "2099-01-01",
                        "summary": "done",
                    }
                ],
                "pending": [],
            }
            (hub / "chats" / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            jsonl = hub / f"{chat_id}.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            reason = bh.should_skip_boundary_distill(
                memory_home=hub, chat_id=chat_id, jsonl=jsonl
            )
            self.assertEqual(reason, "already_distilled")


class TestSessionStart(unittest.TestCase):
    def test_session_start_no_repo_context_inject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats").mkdir()
            (hub / "chats" / "manifest.json").write_text(
                '{"processed":[],"pending":[]}', encoding="utf-8"
            )
            root = Path(tmp) / "proj"
            root.mkdir()
            with mock.patch.object(bh, "run_session_start_catchup") as m:
                m.return_value = {"status": "catchup", "distilled": 0}
                result = bh.handle_session_start(
                    {"workspace_roots": [str(root)]},
                    memory_home=hub,
                )
            self.assertNotIn("additional_context", result)
            self.assertIn("catchup", result)

    def test_catchup_skips_without_workspace_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats").mkdir()
            (hub / "chats" / "manifest.json").write_text(
                '{"processed":[],"pending":[]}', encoding="utf-8"
            )
            out = bh.run_session_start_catchup({"workspace_roots": []}, memory_home=hub)
            self.assertEqual(out["distilled"], 0)
            self.assertEqual(out.get("reason"), "no_workspace_roots")

    def test_catchup_with_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats").mkdir()
            (hub / "chats" / "manifest.json").write_text(
                '{"processed":[],"pending":[]}', encoding="utf-8"
            )
            with mock.patch.object(bh, "list_chats_needing_distill") as list_m:
                list_m.return_value = []
                out = bh.run_session_start_catchup(
                    {"workspace_roots": ["/tmp/MyProject"]},
                    memory_home=hub,
                )
            self.assertEqual(out["distilled"], 0)
            list_m.assert_called_once()


class TestBoundary(unittest.TestCase):
    def test_precompact_user_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats").mkdir()
            (hub / "chats" / "manifest.json").write_text(
                '{"processed":[],"pending":[]}', encoding="utf-8"
            )
            payload = {"hook_event_name": "preCompact"}
            with mock.patch.object(bh, "run_boundary_distill") as m:
                m.return_value = {"status": "skipped", "reason": "no_transcript"}
                result = bh.handle_boundary(payload, memory_home=hub)
            self.assertIn("user_message", result)
            self.assertIn("distills", result["user_message"])

    def test_session_end_no_user_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            payload = {"hook_event_name": "sessionEnd"}
            with mock.patch.object(bh, "run_boundary_distill") as m:
                m.return_value = {"status": "skipped"}
                result = bh.handle_boundary(payload, memory_home=hub)
            self.assertNotIn("user_message", result)


if __name__ == "__main__":
    unittest.main()
