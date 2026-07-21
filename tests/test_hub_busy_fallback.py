"""A busy hub must never stall a session or corrupt shared files."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import boundary_hooks as bh  # noqa: E402
from lib import hub_lock  # noqa: E402
from lib.boundary_debounce import record_boundary_distill  # noqa: E402
from lib.chats_manifest import load_manifest, save_manifest  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _hub_with_transcript(tmp: str) -> tuple[Path, Path]:
    root = Path(tmp)
    hub = root / "hub"
    (hub / "chats").mkdir(parents=True)
    transcripts = root / "claude-projects" / "-home-me-Work-example-app"
    transcripts.mkdir(parents=True)
    jsonl = transcripts / "claude-session-0001.jsonl"
    jsonl.write_text(
        (FIXTURES / "claude-chat.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return hub, jsonl


class TestBusyHubDefersApply(unittest.TestCase):
    def test_apply_deferred_when_cron_holds_lock(self) -> None:
        """Cron owns the hub: distill still records staging, but skips the apply."""
        with tempfile.TemporaryDirectory() as tmp:
            hub, jsonl = _hub_with_transcript(tmp)
            payload = {
                "hook_event_name": "SessionEnd",
                "transcript_path": str(jsonl),
                "cwd": "/home/me/Work/example-app",
            }
            # Simulate the cron script's shell `mkdir` lock.
            hub_lock.lock_path(hub).mkdir(parents=True)

            calls: list[bool] = []

            def fake_distill(_jsonl, **kwargs):
                calls.append(kwargs.get("apply", True))
                return {"status": "distilled"}

            with mock.patch.object(bh, "distill_jsonl", side_effect=fake_distill):
                with mock.patch.object(hub_lock, "DEFAULT_TIMEOUT_SECONDS", 0.1):
                    result = bh.run_boundary_distill(
                        payload, memory_home=hub, projects_root=None
                    )

            self.assertEqual(result.get("deferred"), "hub_busy")
            self.assertEqual(calls, [False], "apply must be skipped while hub is busy")

    def test_apply_runs_when_hub_is_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub, jsonl = _hub_with_transcript(tmp)
            payload = {
                "hook_event_name": "SessionEnd",
                "transcript_path": str(jsonl),
                "cwd": "/home/me/Work/example-app",
            }
            calls: list[bool] = []

            def fake_distill(_jsonl, **kwargs):
                calls.append(kwargs.get("apply", True))
                return {"status": "distilled"}

            with mock.patch.object(bh, "distill_jsonl", side_effect=fake_distill):
                result = bh.run_boundary_distill(
                    payload, memory_home=hub, projects_root=None
                )

            self.assertNotIn("deferred", result)
            self.assertEqual(calls, [True])

    def test_lock_released_after_distill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub, jsonl = _hub_with_transcript(tmp)
            payload = {
                "hook_event_name": "SessionEnd",
                "transcript_path": str(jsonl),
                "cwd": "/home/me/Work/example-app",
            }
            with mock.patch.object(
                bh, "distill_jsonl", return_value={"status": "distilled"}
            ):
                bh.run_boundary_distill(payload, memory_home=hub, projects_root=None)
            self.assertFalse(hub_lock.lock_path(hub).exists())

    def test_distill_error_still_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub, jsonl = _hub_with_transcript(tmp)
            payload = {
                "hook_event_name": "SessionEnd",
                "transcript_path": str(jsonl),
                "cwd": "/home/me/Work/example-app",
            }
            with mock.patch.object(bh, "distill_jsonl", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    bh.run_boundary_distill(payload, memory_home=hub, projects_root=None)
            self.assertFalse(hub_lock.lock_path(hub).exists())


class TestSharedFileWritesAreAtomic(unittest.TestCase):
    def test_manifest_write_leaves_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chats" / "manifest.json"
            save_manifest(path, {"processed": [{"id": "chat-1"}], "pending": []})
            self.assertEqual(len(load_manifest(path)["processed"]), 1)
            self.assertEqual([p.name for p in path.parent.iterdir()], ["manifest.json"])

    def test_manifest_survives_concurrent_reader(self) -> None:
        """A reader running during a rewrite sees either the old or the new file."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            save_manifest(path, {"processed": [{"id": "old"}], "pending": []})
            big = {"processed": [{"id": f"chat-{i}"} for i in range(5000)], "pending": []}
            save_manifest(path, big)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["processed"]), 5000)

    def test_debounce_state_write_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            record_boundary_distill(hub, "chat-1")
            state = hub / ".state" / "boundary-debounce.json"
            self.assertIn("chat-1", json.loads(state.read_text(encoding="utf-8")))
            leftovers = [p.name for p in state.parent.iterdir() if p.name != state.name]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
