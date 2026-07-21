"""Claude Code plugin surface — manifests, hook config, and prompt-submit routing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import boundary_hooks as bh  # noqa: E402
from lib import routing_context as rc  # noqa: E402

PLUGIN_MANIFEST = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
HOOKS_JSON = REPO / "hooks" / "claude" / "hooks.json"
HOOK_SCRIPT = REPO / "hooks" / "claude" / "agent-memory-hook.sh"


class TestManifests(unittest.TestCase):
    def test_plugin_manifest_valid(self) -> None:
        data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "agent-memory")
        self.assertEqual(data["hooks"], "./hooks/claude/hooks.json")
        self.assertEqual(data["skills"], "./skills/")

    def test_version_matches_cursor_manifest_and_version_file(self) -> None:
        """Both manifests ship from one repo — a version skew is a packaging bug."""
        claude = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
        cursor = json.loads(
            (REPO / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        version_file = (REPO / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(claude, cursor)
        self.assertEqual(claude, version_file)

    def test_cursor_manifest_stays_out_of_bundle_root(self) -> None:
        """Claude Code probes hooks/hooks.json itself and rejects Cursor's event
        names (afterFileEdit), breaking `claude plugin list`. Each environment
        keeps its manifest in its own subdirectory."""
        self.assertFalse((REPO / "hooks" / "hooks.json").exists())
        cursor = json.loads(
            (REPO / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(cursor["hooks"], "./hooks/cursor/hooks.json")
        self.assertTrue((REPO / "hooks" / "cursor" / "hooks.json").exists())

    def test_marketplace_points_at_repo_root(self) -> None:
        data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        self.assertEqual(data["plugins"][0]["name"], "agent-memory")
        self.assertEqual(data["plugins"][0]["source"], "./")


class TestHookConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]

    def test_declared_events_are_handled(self) -> None:
        """Every declared event must map to a canonical event we actually route."""
        for event in self.hooks:
            canonical = bh.canonical_event({"hook_event_name": event})
            self.assertIn(
                canonical,
                bh.BOUNDARY_EVENTS | bh.LIVE_EVENTS | {"sessionStart", "promptSubmit"},
                f"{event} -> {canonical} is not routed",
            )

    def test_commands_use_plugin_root(self) -> None:
        for event, entries in self.hooks.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}", hook["command"], event)
                    self.assertEqual(hook["type"], "command")

    def test_precompact_covers_auto_and_manual(self) -> None:
        """auto is the context-limit trigger — the case memory must survive."""
        self.assertEqual(self.hooks["PreCompact"][0]["matcher"], "auto|manual")

    def test_hook_script_is_executable(self) -> None:
        self.assertTrue(os.access(HOOK_SCRIPT, os.X_OK))


class TestHookScript(unittest.TestCase):
    """Every case here must keep its log inside tmp — a test may not write to ~/.claude."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.log = self.tmp / "hook.log"
        self.addCleanup(self._tmp.cleanup)

    def _run(self, stdin: str, *args: str) -> subprocess.CompletedProcess:
        env = dict(
            os.environ,
            CLAUDE_PLUGIN_ROOT=str(REPO),
            AGENT_MEMORY_CLAUDE_HOOK_LOG=str(self.log),
            MEMORY_HOME=str(self.tmp / "hub"),
        )
        return subprocess.run(
            ["bash", str(HOOK_SCRIPT), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_always_exits_zero_and_prints_json(self) -> None:
        """A memory plugin must never break the session it is remembering."""
        proc = self._run(
            json.dumps({"hook_event_name": "SessionEnd", "cwd": "/tmp/example-app"})
        )
        self.assertEqual(proc.returncode, 0)
        json.loads(proc.stdout)

    def test_garbage_input_is_survivable(self) -> None:
        proc = self._run("not json at all")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {})
        log = self.log.read_text(encoding="utf-8")
        # Must not echo raw stdin — prompts / cwd can live in the first 80 bytes.
        self.assertNotIn("not json at all", log)
        self.assertIn("payload not logged", log)

    def test_empty_stdin_is_reported_distinctly(self) -> None:
        """'harness sent nothing' must not look like 'payload was malformed'."""
        proc = self._run("")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {})
        log = self.log.read_text(encoding="utf-8")
        self.assertIn("empty stdin", log)
        self.assertIn("stdin=0B", log)

    def test_mode_derived_from_payload_without_args(self) -> None:
        """`args` support is not guaranteed; SessionStart must still bootstrap."""
        self._run(json.dumps({"hook_event_name": "SessionStart", "source": "startup"}))
        self.assertIn("session-start", self.log.read_text(encoding="utf-8"))

    def test_non_session_start_events_use_boundary(self) -> None:
        for event in ("Stop", "SessionEnd", "PreCompact", "UserPromptSubmit"):
            with self.subTest(event=event):
                self.log.unlink(missing_ok=True)
                self._run(json.dumps({"hook_event_name": event}))
                line = self.log.read_text(encoding="utf-8").splitlines()[0]
                self.assertIn("boundary", line)
                self.assertIn(f"event={event}", line)

    def test_explicit_arg_overrides_payload(self) -> None:
        self._run(json.dumps({"hook_event_name": "Stop"}), "session-start")
        self.assertIn("session-start", self.log.read_text(encoding="utf-8"))

    def test_does_not_write_to_real_home(self) -> None:
        """Regression: an earlier version of this test polluted ~/.claude."""
        real_log = Path.home() / ".claude" / "agent-memory-hook.log"
        before = real_log.stat().st_mtime if real_log.exists() else None
        self._run(json.dumps({"hook_event_name": "Stop"}))
        after = real_log.stat().st_mtime if real_log.exists() else None
        self.assertEqual(before, after)


class TestPromptSubmitRouting(unittest.TestCase):
    def _hub_with_thread(self, tmp: str) -> Path:
        hub = Path(tmp) / "hub"
        projects = hub / "chats" / "projects"
        projects.mkdir(parents=True)
        (projects / "example-app.md").write_text(
            "# example-app\n_Last updated: 2026-07-20_\n\n"
            "## Open threads\n\n"
            "- **[deploy]** finish staging rollout · _upd 2026-07-20_\n",
            encoding="utf-8",
        )
        return hub

    def test_threads_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_thread(tmp)
            text = rc.render_open_threads(hub)
            self.assertIn("finish staging rollout", text)
            self.assertIn("deploy", text)

    def test_empty_hub_renders_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            (hub / "chats" / "projects").mkdir(parents=True)
            self.assertIsNone(rc.render_open_threads(hub))

    def test_prompt_submit_injects_then_debounces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_thread(tmp)
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "claude-session-0001",
                "cwd": str(Path(tmp) / "example-app"),
            }
            first = bh.handle_boundary(payload, memory_home=hub)
            self.assertEqual(first["status"], "injected")
            self.assertIn("finish staging rollout", first["user_message"])

            second = bh.handle_boundary(payload, memory_home=hub)
            self.assertEqual(second["status"], "skipped")
            self.assertEqual(second["reason"], "debounced")

    def test_other_writer_beats_the_debounce(self) -> None:
        """The hub has two writers on independent schedules: a thread Cursor's
        cron just wrote must not wait out this session's 30-minute debounce."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_thread(tmp)
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "claude-session-0004",
                "cwd": str(Path(tmp) / "example-app"),
            }
            self.assertEqual(bh.handle_boundary(payload, memory_home=hub)["status"], "injected")
            self.assertEqual(bh.handle_boundary(payload, memory_home=hub)["status"], "skipped")

            project = hub / "chats" / "projects" / "other-app.md"
            project.write_text(
                "# other-app\n_Last updated: 2026-07-21_\n\n## Open threads\n\n"
                "- **[api]** written by the other agent · _upd 2026-07-21_\n",
                encoding="utf-8",
            )
            result = bh.handle_boundary(payload, memory_home=hub)
            self.assertEqual(result["status"], "injected")
            self.assertIn("written by the other agent", result["user_message"])

    def test_quiet_hub_stays_debounced(self) -> None:
        """Re-injecting on a hub nobody wrote to would just be noise."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_thread(tmp)
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "claude-session-0005",
                "cwd": str(Path(tmp) / "example-app"),
            }
            bh.handle_boundary(payload, memory_home=hub)
            for _ in range(3):
                self.assertEqual(
                    bh.handle_boundary(payload, memory_home=hub)["reason"], "debounced"
                )

    def test_injected_context_uses_claude_output_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_thread(tmp)
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "claude-session-0002",
                "cwd": str(Path(tmp) / "example-app"),
            }
            result = bh.handle_boundary(payload, memory_home=hub)
            out = bh.format_hook_output(payload, result)
            self.assertEqual(
                out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
            )
            self.assertIn("Open threads", out["hookSpecificOutput"]["additionalContext"])

    def test_prompt_submit_never_distills(self) -> None:
        """Injection is read-only — no manifest, no staging, no project write."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_thread(tmp)
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "claude-session-0003",
                "cwd": str(Path(tmp) / "example-app"),
            }
            bh.handle_boundary(payload, memory_home=hub)
            self.assertFalse((hub / "chats" / "manifest.json").exists())
            self.assertFalse((hub / "chats" / "merge-staging").exists())


if __name__ == "__main__":
    unittest.main()
