"""Tests for environment dispatch in scripts/lib/boundary_hooks.py"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import boundary_hooks as bh  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

CLAUDE_PAYLOAD = {
    "hook_event_name": "SessionEnd",
    "session_id": "claude-session-0001",
    "cwd": "/home/example-user/Work/example-app",
    "reason": "other",
}
CURSOR_PAYLOAD = {
    "hook_event_name": "sessionEnd",
    "conversation_id": "cursor-chat-0001",
    "workspace_roots": ["/home/example-user/Work/example-app"],
}


class TestEnvResolution(unittest.TestCase):
    def test_claude_payload_detected_without_env_marker(self) -> None:
        """A CamelCase harness event is enough to recognize Claude."""
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ("AGENT_MEMORY_ENV", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR"):
                os.environ.pop(key, None)
            self.assertEqual(bh.resolve_env(CLAUDE_PAYLOAD).name, "claude")
            self.assertEqual(bh.resolve_env(CURSOR_PAYLOAD).name, "cursor")

    def test_explicit_env_var_wins(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_MEMORY_ENV": "claude"}, clear=False):
            self.assertEqual(bh.resolve_env(CURSOR_PAYLOAD).name, "claude")


class TestCanonicalEvent(unittest.TestCase):
    def test_claude_events_normalized(self) -> None:
        cases = {
            "SessionStart": "sessionStart",
            "SessionEnd": "sessionEnd",
            "PreCompact": "preCompact",
            "Stop": "liveDistill",
            "PostToolUse": "afterFileEdit",
            "UserPromptSubmit": "promptSubmit",
        }
        for raw, canonical in cases.items():
            payload = dict(CLAUDE_PAYLOAD, hook_event_name=raw)
            self.assertEqual(bh.canonical_event(payload), canonical, raw)

    def test_cursor_events_unchanged(self) -> None:
        self.assertEqual(bh.canonical_event(CURSOR_PAYLOAD), "sessionEnd")

    def test_unknown_event_passes_through(self) -> None:
        payload = dict(CURSOR_PAYLOAD, hook_event_name="Elicitation")
        self.assertEqual(bh.canonical_event(payload), "Elicitation")

    def test_missing_event_name(self) -> None:
        self.assertEqual(bh.canonical_event({}), "boundary")


class TestWorkspaceRoots(unittest.TestCase):
    def test_claude_cwd_becomes_workspace_root(self) -> None:
        self.assertEqual(
            bh.workspace_roots(CLAUDE_PAYLOAD), ["/home/example-user/Work/example-app"]
        )

    def test_cursor_list_preserved(self) -> None:
        self.assertEqual(
            bh.workspace_roots(CURSOR_PAYLOAD), ["/home/example-user/Work/example-app"]
        )


class TestHookOutput(unittest.TestCase):
    def test_claude_gets_hook_specific_output(self) -> None:
        out = bh.format_hook_output(CLAUDE_PAYLOAD, {"user_message": "curate threads"})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionEnd")
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], "curate threads")

    def test_cursor_gets_user_message(self) -> None:
        out = bh.format_hook_output(CURSOR_PAYLOAD, {"user_message": "curate threads"})
        self.assertEqual(out, {"user_message": "curate threads"})

    def test_no_message_yields_empty_object(self) -> None:
        self.assertEqual(bh.format_hook_output(CLAUDE_PAYLOAD, {"status": "ok"}), {})


class TestBoundaryRouting(unittest.TestCase):
    def _hub(self, tmp: str) -> Path:
        hub = Path(tmp) / "hub"
        (hub / "chats" / "projects").mkdir(parents=True)
        return hub

    def test_stop_routes_to_live_distill(self) -> None:
        """Claude's per-turn Stop must never apply to the project file."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub(tmp)
            payload = dict(CLAUDE_PAYLOAD, hook_event_name="Stop")
            with mock.patch.object(
                bh, "_run_live_distill_for", return_value={"status": "distilled"}
            ) as live:
                result = bh.handle_boundary(payload, memory_home=hub)
            self.assertEqual(result["event"], "liveDistill")
            self.assertEqual(result["env"], "claude")
            self.assertEqual(result["live_distill"], {"status": "distilled"})
            live.assert_called_once()

    def test_prompt_submit_is_not_a_distill_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub(tmp)
            payload = dict(CLAUDE_PAYLOAD, hook_event_name="UserPromptSubmit")
            result = bh.handle_boundary(payload, memory_home=hub)
            self.assertEqual(result["status"], "ignored")
            self.assertEqual(result["event"], "promptSubmit")

    def test_claude_session_end_reaches_boundary_distill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub(tmp)
            with mock.patch.object(
                bh, "run_boundary_distill", return_value={"status": "skipped"}
            ) as distill:
                result = bh.handle_boundary(CLAUDE_PAYLOAD, memory_home=hub)
            self.assertEqual(result["event"], "sessionEnd")
            distill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
