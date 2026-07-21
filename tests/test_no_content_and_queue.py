"""Alerts must mean something: a contentless chat is not a failure, and the
curation queue must not repeat one project or point at files that are gone."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, minimal_hub

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib import boundary_hooks as bh  # noqa: E402
from lib.chats_manifest import load_manifest, processed_by_id  # noqa: E402
from lib.pending_chats import needs_distill  # noqa: E402
from lib.pointer_curation_queue import enqueue, list_pending  # noqa: E402
from lib.transcript import TranscriptEmptyError, TranscriptSchemaError  # noqa: E402


#: A real capture: a slash-command run, valid jsonl, zero conversation.
COMMAND_ONLY = (
    '{"type":"file-history-snapshot"}\n'
    '{"role":"user","message":{"role":"user","content":'
    '"<command-name>/mcp</command-name>"}}\n'
    '{"role":"user","message":{"role":"user","content":'
    '"<local-command-stdout>Connected.</local-command-stdout>"}}\n'
)


class TestEmptyTranscript(unittest.TestCase):
    def test_empty_is_a_kind_of_schema_error(self) -> None:
        """Callers catching the broad error keep working."""
        self.assertTrue(issubclass(TranscriptEmptyError, TranscriptSchemaError))

    def test_contentless_chat_is_skipped_not_errored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub)
            jsonl = Path(tmp) / "9aad1d4c.jsonl"
            jsonl.write_text(COMMAND_ONLY, encoding="utf-8")

            out = bh.distill_jsonl(
                jsonl, memory_home=hub, projects_root=Path(tmp), apply=False
            )
            self.assertEqual(out["status"], "skipped")
            self.assertEqual(out["reason"], "no_content")

    def test_contentless_chat_stops_being_pending(self) -> None:
        """It stayed pending forever and kept `errors` above zero, so a healthy
        hub reported a warning on every status call."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub)
            jsonl = Path(tmp) / "9aad1d4c.jsonl"
            jsonl.write_text(COMMAND_ONLY, encoding="utf-8")

            bh.distill_jsonl(jsonl, memory_home=hub, projects_root=Path(tmp), apply=False)

            manifest = load_manifest(hub / "chats" / "manifest.json")
            entry = processed_by_id(manifest).get("9aad1d4c")
            self.assertIsNotNone(entry)
            self.assertEqual(entry["status"], "no_content")
            self.assertFalse(needs_distill("9aad1d4c", jsonl, manifest))

    def test_growing_content_makes_it_pending_again(self) -> None:
        """Marking it examined must not bury a chat that later gets real use."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            minimal_hub(hub)
            jsonl = Path(tmp) / "9aad1d4c.jsonl"
            jsonl.write_text(COMMAND_ONLY, encoding="utf-8")
            bh.distill_jsonl(jsonl, memory_home=hub, projects_root=Path(tmp), apply=False)

            with jsonl.open("a", encoding="utf-8") as fh:
                for i in range(4):
                    fh.write(
                        json.dumps(
                            {"role": "user", "message": {"role": "user",
                                                         "content": f"real question {i}"}}
                        )
                        + "\n"
                    )
            manifest = load_manifest(hub / "chats" / "manifest.json")
            self.assertTrue(needs_distill("9aad1d4c", jsonl, manifest))


class TestCurationQueue(unittest.TestCase):
    def _hub(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hub = Path(tmp.name) / "hub"
        minimal_hub(hub)
        return hub

    def test_one_entry_per_project(self) -> None:
        """Four chats touching one file is one curation job, not four lines."""
        hub = self._hub()
        staging = hub / "chats" / "merge-staging"
        staging.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            path = staging / f"s{i}.md"
            path.write_text("x", encoding="utf-8")
            enqueue(
                hub,
                chat_id=f"chat-{i}",
                project_rel="projects/example-app.md",
                reason="open-thread-draft",
                staging_path=str(path),
                kind="open-thread",
            )
        self.assertEqual(len(list_pending(hub, kind="open-thread")), 1)

    def test_entries_with_a_missing_staging_file_are_dropped(self) -> None:
        """After a hub move every stale entry points at a path that is gone."""
        hub = self._hub()
        enqueue(
            hub,
            chat_id="chat-x",
            project_rel="projects/other-app.md",
            reason="open-thread-draft",
            staging_path=str(hub / "chats" / "merge-staging" / "vanished.md"),
            kind="open-thread",
        )
        self.assertEqual(list_pending(hub, kind="open-thread"), [])


if __name__ == "__main__":
    unittest.main()
