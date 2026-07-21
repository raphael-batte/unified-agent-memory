"""Tests for scripts/lib/envs/ — one module per agent harness."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import envs  # noqa: E402
from lib.envs import base  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


class TestRegistry(unittest.TestCase):
    def test_known_envs(self) -> None:
        names = {e.name for e in envs.all_envs()}
        self.assertEqual(names, {"cursor", "claude"})

    def test_get_env_unknown(self) -> None:
        with self.assertRaises(ValueError):
            envs.get_env("codex")

    def test_trigger_kinds_differ(self) -> None:
        """Cursor lost hook support — it is cron driven; Claude is event driven."""
        self.assertEqual(envs.CURSOR_ENV.trigger_kind, base.TRIGGER_CRON)
        self.assertEqual(envs.CLAUDE_ENV.trigger_kind, base.TRIGGER_HOOKS)

    def test_anchors_are_distinct(self) -> None:
        self.assertNotEqual(envs.CURSOR_ENV.anchor_dir(), envs.CLAUDE_ENV.anchor_dir())


class TestDetectEnv(unittest.TestCase):
    def test_explicit_override_wins(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_MEMORY_ENV": "claude"}, clear=False):
            self.assertEqual(envs.detect_env().name, "claude")
        with mock.patch.dict(os.environ, {"AGENT_MEMORY_ENV": "cursor"}, clear=False):
            self.assertEqual(envs.detect_env().name, "cursor")

    def test_claude_plugin_root_marker(self) -> None:
        env = {"CLAUDE_PLUGIN_ROOT": "/tmp/plugin"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AGENT_MEMORY_ENV", None)
            self.assertEqual(envs.detect_env().name, "claude")

    def test_defaults_to_cursor(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ("AGENT_MEMORY_ENV", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR"):
                os.environ.pop(key, None)
            self.assertEqual(envs.detect_env().name, "cursor")

    def test_unknown_override_raises(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_MEMORY_ENV": "nope"}, clear=False):
            with self.assertRaises(ValueError):
                envs.detect_env()


class TestTranscriptRoots(unittest.TestCase):
    def test_root_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ, {"AGENT_MEMORY_CLAUDE_PROJECTS": tmp}, clear=False
            ):
                self.assertEqual(envs.CLAUDE_ENV.transcript_root(), Path(tmp))
                self.assertTrue(envs.CLAUDE_ENV.is_available())

    def test_available_envs_filters_missing_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "absent")
            with mock.patch.dict(
                os.environ,
                {
                    "AGENT_MEMORY_CURSOR_PROJECTS": tmp,
                    "AGENT_MEMORY_CLAUDE_PROJECTS": missing,
                },
                clear=False,
            ):
                names = {e.name for e in envs.available_envs()}
                self.assertEqual(names, {"cursor"})

    def test_transcript_roots_deduped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                {
                    "AGENT_MEMORY_CURSOR_PROJECTS": tmp,
                    "AGENT_MEMORY_CLAUDE_PROJECTS": tmp,
                },
                clear=False,
            ):
                self.assertEqual(envs.transcript_roots(), [Path(tmp)])


class TestEventNormalization(unittest.TestCase):
    def test_claude_events_map_to_canonical(self) -> None:
        cases = {
            "SessionStart": base.EVENT_SESSION_START,
            "UserPromptSubmit": base.EVENT_PROMPT_SUBMIT,
            "Stop": base.EVENT_LIVE_DISTILL,
            "PreCompact": base.EVENT_PRE_COMPACT,
            "SessionEnd": base.EVENT_SESSION_END,
            "PostToolUse": base.EVENT_AFTER_EDIT,
        }
        for harness_event, canonical in cases.items():
            got = envs.CLAUDE_ENV.normalize_event({"hook_event_name": harness_event})
            self.assertEqual(got, canonical, harness_event)
            self.assertIn(got, base.CANONICAL_EVENTS)

    def test_claude_unknown_event_ignored(self) -> None:
        self.assertIsNone(envs.CLAUDE_ENV.normalize_event({"hook_event_name": "Elicitation"}))
        self.assertIsNone(envs.CLAUDE_ENV.normalize_event({}))

    def test_cursor_events_pass_through(self) -> None:
        self.assertEqual(
            envs.CURSOR_ENV.normalize_event({"hook_event_name": "sessionEnd"}),
            base.EVENT_SESSION_END,
        )
        self.assertIsNone(envs.CURSOR_ENV.normalize_event({"hook_event_name": "SessionEnd"}))


class TestWorkspaceRoots(unittest.TestCase):
    def test_claude_uses_cwd(self) -> None:
        """Claude sends a single cwd where Cursor sends workspace_roots."""
        roots = envs.CLAUDE_ENV.workspace_roots({"cwd": "/home/example-user/Work/example-app"})
        self.assertEqual(roots, ["/home/example-user/Work/example-app"])

    def test_claude_falls_back_to_workspace_roots(self) -> None:
        roots = envs.CLAUDE_ENV.workspace_roots({"workspace_roots": ["/srv/example-app"]})
        self.assertEqual(roots, ["/srv/example-app"])

    def test_cursor_uses_workspace_roots(self) -> None:
        roots = envs.CURSOR_ENV.workspace_roots({"workspace_roots": ["/srv/example-app"]})
        self.assertEqual(roots, ["/srv/example-app"])

    def test_empty_payload(self) -> None:
        self.assertEqual(envs.CLAUDE_ENV.workspace_roots({}), [])
        self.assertEqual(envs.CURSOR_ENV.workspace_roots({"workspace_roots": "bad"}), [])


class TestOutputShape(unittest.TestCase):
    def test_claude_wraps_in_hook_specific_output(self) -> None:
        out = envs.CLAUDE_ENV.format_output(
            base.EVENT_SESSION_START, {"user_message": "Open threads: ship example-app"}
        )
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(
            out["hookSpecificOutput"]["additionalContext"], "Open threads: ship example-app"
        )

    def test_cursor_uses_user_message(self) -> None:
        out = envs.CURSOR_ENV.format_output(base.EVENT_SESSION_END, {"user_message": "hi"})
        self.assertEqual(out, {"user_message": "hi"})

    def test_empty_result_is_empty_object(self) -> None:
        for env in envs.all_envs():
            self.assertEqual(env.format_output(base.EVENT_SESSION_END, {}), {})


class TestTranscriptIndexDelegation(unittest.TestCase):
    def test_each_env_reads_its_own_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            cursor_dir = root / "cursor" / "example-app" / "agent-transcripts"
            cursor_dir.mkdir(parents=True)
            (cursor_dir / "cursor-chat-0001.jsonl").write_text(
                (FIXTURES / "sample-chat.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            claude_dir = root / "claude" / "-home-example-user-Work-example-app"
            claude_dir.mkdir(parents=True)
            (claude_dir / "claude-session-0001.jsonl").write_text(
                (FIXTURES / "claude-chat.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            cursor_index = envs.CURSOR_ENV.build_transcript_index(root / "cursor")
            claude_index = envs.CLAUDE_ENV.build_transcript_index(root / "claude")

            self.assertIn("cursor-chat-0001", cursor_index)
            self.assertIn("claude-session-0001", claude_index)
            # Layouts must not bleed into each other.
            self.assertNotIn("claude-session-0001", cursor_index)
            self.assertNotIn("cursor-chat-0001", claude_index)


if __name__ == "__main__":
    unittest.main()
