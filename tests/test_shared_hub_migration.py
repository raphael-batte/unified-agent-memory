"""Tests for `migrate-memory.py --to-shared` and the multi-anchor write."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import memory_config as mc  # noqa: E402

MIGRATE = SCRIPTS / "migrate-memory.py"


def _seed_hub(hub: Path) -> None:
    (hub / "context").mkdir(parents=True)
    (hub / "feedback").mkdir()
    (hub / "chats" / "projects").mkdir(parents=True)
    (hub / "context" / "GLOBAL_CONTEXT.md").write_text(
        "# Global Context\n\n## Me\n- example user\n", encoding="utf-8"
    )
    (hub / "chats" / "projects" / "example-app.md").write_text(
        "# example-app\n_Last updated: 2026-07-20_\n\n"
        "## Open threads\n\n- **[deploy]** finish staging rollout · _upd 2026-07-20_\n",
        encoding="utf-8",
    )
    (hub / "chats" / "manifest.json").write_text(
        json.dumps({"processed": [{"id": "chat-1", "env": "cursor"}], "pending": []}),
        encoding="utf-8",
    )


class TestPersistAllAnchors(unittest.TestCase):
    def test_every_environment_anchor_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fake-home"
            hub = Path(tmp) / "shared"
            hub.mkdir()
            with mock.patch.dict(
                os.environ, {"AGENT_MEMORY_ANCHOR_HOME": str(home)}, clear=False
            ):
                written = mc.persist_all_anchors(hub)
                self.assertEqual(len(written), 2)
                for path in written:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(data["memory_home"], str(hub.resolve()))

    def test_existing_anchor_keys_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fake-home"
            anchor = home / ".cursor" / "agent-memory"
            anchor.mkdir(parents=True)
            (anchor / "config.json").write_text(
                json.dumps({"plugin_root": "/opt/agent-memory"}), encoding="utf-8"
            )
            hub = Path(tmp) / "shared"
            hub.mkdir()
            with mock.patch.dict(
                os.environ, {"AGENT_MEMORY_ANCHOR_HOME": str(home)}, clear=False
            ):
                mc.persist_all_anchors(hub)
            data = json.loads((anchor / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(data["plugin_root"], "/opt/agent-memory")
            self.assertEqual(data["memory_home"], str(hub.resolve()))


class TestToSharedCLI(unittest.TestCase):
    def _run(self, home: Path, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, AGENT_MEMORY_ANCHOR_HOME=str(home))
        env.pop("MEMORY_HOME", None)
        return subprocess.run(
            [sys.executable, str(MIGRATE), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_migrates_legacy_hub_and_writes_both_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fake-home"
            legacy = home / ".cursor" / "agent-memory"
            _seed_hub(legacy)
            shared = home / ".agent-memory"

            proc = self._run(home, "--to-shared")
            self.assertEqual(proc.returncode, 0, proc.stderr)

            self.assertTrue((shared / "chats" / "projects" / "example-app.md").is_file())
            for rel in (".cursor/agent-memory", ".claude/agent-memory"):
                data = json.loads((home / rel / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(data["memory_home"], str(shared.resolve()))

    def test_idempotent_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fake-home"
            _seed_hub(home / ".cursor" / "agent-memory")
            self.assertEqual(self._run(home, "--to-shared").returncode, 0)
            second = self._run(home, "--to-shared")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("Already on the shared hub", second.stdout)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fake-home"
            _seed_hub(home / ".cursor" / "agent-memory")
            proc = self._run(home, "--to-shared", "--dry-run")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse((home / ".agent-memory").exists())

    def test_from_still_required_without_to_shared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(Path(tmp) / "fake-home")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--to-shared", proc.stderr)


class TestListChatsJson(unittest.TestCase):
    def test_json_inventory_reports_env(self) -> None:
        fixtures = REPO / "tests" / "fixtures"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hub = root / "hub"
            (hub / "chats").mkdir(parents=True)

            cursor_root = root / "cursor-projects"
            (cursor_root / "Users-me-Work-example-app" / "agent-transcripts").mkdir(
                parents=True
            )
            (
                cursor_root
                / "Users-me-Work-example-app"
                / "agent-transcripts"
                / "chat-cursor-1.jsonl"
            ).write_text(
                (fixtures / "sample-chat.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            claude_root = root / "claude-projects"
            (claude_root / "-home-me-Work-example-app").mkdir(parents=True)
            (
                claude_root / "-home-me-Work-example-app" / "claude-session-1.jsonl"
            ).write_text(
                (fixtures / "claude-chat.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            env = dict(
                os.environ,
                MEMORY_HOME=str(hub),
                AGENT_MEMORY_CURSOR_PROJECTS=str(cursor_root),
                AGENT_MEMORY_CLAUDE_PROJECTS=str(claude_root),
            )
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "list-chats.py"), "--json"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rows = json.loads(proc.stdout)
            self.assertEqual({r["env"] for r in rows}, {"cursor", "claude"})
            self.assertTrue(all("distilled" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
