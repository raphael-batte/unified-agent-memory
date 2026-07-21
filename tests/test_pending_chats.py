"""Tests for scripts/lib/pending_chats.py"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from helpers import minimal_hub

from lib import pending_chats as pc  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _make_cursor_transcript(root: Path, workspace: str, chat_id: str) -> Path:
    d = root / workspace / "agent-transcripts"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{chat_id}.jsonl"
    path.write_text(
        (FIXTURES / "sample-chat.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return path


def _make_claude_transcript(root: Path, workspace: str, chat_id: str) -> Path:
    d = root / workspace
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{chat_id}.jsonl"
    path.write_text(
        (FIXTURES / "claude-chat.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return path


class TestMultiEnvScan(unittest.TestCase):
    """The hub is shared, so a scan must cover every installed environment."""

    def test_scan_covers_both_envs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cursor_root = root / "cursor-projects"
            claude_root = root / "claude-projects"
            _make_cursor_transcript(cursor_root, "Users-me-Work-example-app", "chat-cursor-1")
            _make_claude_transcript(claude_root, "-home-me-Work-example-app", "chat-claude-1")

            with mock.patch.dict(
                os.environ,
                {
                    "AGENT_MEMORY_CURSOR_PROJECTS": str(cursor_root),
                    "AGENT_MEMORY_CLAUDE_PROJECTS": str(claude_root),
                },
                clear=False,
            ):
                rows = pc.scan_transcript_rows()

            by_env = {r["env"]: r for r in rows}
            self.assertEqual(set(by_env), {"cursor", "claude"})
            self.assertEqual(by_env["cursor"]["id"], "chat-cursor-1")
            self.assertEqual(by_env["claude"]["id"], "chat-claude-1")

    def test_project_slug_shared_across_envs(self) -> None:
        """Same repo in both environments must land on one project file."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cursor_root = root / "cursor-projects"
            claude_root = root / "claude-projects"
            _make_cursor_transcript(cursor_root, "Users-me-Work-example-app", "chat-cursor-1")
            _make_claude_transcript(claude_root, "-home-me-Work-example-app", "chat-claude-1")

            with mock.patch.dict(
                os.environ,
                {
                    "AGENT_MEMORY_CURSOR_PROJECTS": str(cursor_root),
                    "AGENT_MEMORY_CLAUDE_PROJECTS": str(claude_root),
                },
                clear=False,
            ):
                rows = pc.scan_transcript_rows()

            self.assertEqual({r["project"] for r in rows}, {"example-app"})

    def test_missing_env_root_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cursor_root = root / "cursor-projects"
            _make_cursor_transcript(cursor_root, "Users-me-Work-example-app", "chat-cursor-1")

            with mock.patch.dict(
                os.environ,
                {
                    "AGENT_MEMORY_CURSOR_PROJECTS": str(cursor_root),
                    "AGENT_MEMORY_CLAUDE_PROJECTS": str(root / "absent"),
                },
                clear=False,
            ):
                rows = pc.scan_transcript_rows()

            self.assertEqual([r["env"] for r in rows], ["cursor"])

    def test_explicit_root_probes_both_layouts(self) -> None:
        """Callers passing a single root keep working — layouts are disjoint."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_cursor_transcript(root, "Users-me-Work-example-app", "chat-cursor-1")
            rows = pc.scan_transcript_rows(root)
            self.assertEqual([r["env"] for r in rows], ["cursor"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_claude_transcript(root, "-home-me-Work-example-app", "chat-claude-1")
            rows = pc.scan_transcript_rows(root)
            self.assertEqual([r["env"] for r in rows], ["claude"])

    def test_subagent_transcripts_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_cursor_transcript(root, "Users-me-Work-example-app", "chat-cursor-1")
            sub = root / "Users-me-Work-example-app" / "agent-transcripts" / "subagents"
            sub.mkdir(parents=True)
            (sub / "chat-sub-1.jsonl").write_text(
                (FIXTURES / "sample-chat.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            rows = pc.scan_transcript_rows(root)
            self.assertEqual([r["id"] for r in rows], ["chat-cursor-1"])


class TestPendingChats(unittest.TestCase):
    def test_needs_distill_new_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            manifest = {"processed": [], "pending": []}
            self.assertTrue(pc.needs_distill("a", jsonl, manifest))

    def test_slugs_from_workspace_roots(self) -> None:
        slugs = pc.slugs_from_workspace_roots(["/tmp/workspaces/example-app"])
        self.assertIn("example-app", slugs)

    def test_filter_by_days(self) -> None:
        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        rows = [{"date": old, "mtime": 0}, {"date": "2099-01-01", "mtime": 1}]
        filtered = pc.filter_by_days(rows, 180)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["date"], "2099-01-01")

    def test_order_for_distill_oldest_first(self) -> None:
        rows = [
            {"id": "new", "mtime": 200.0, "date": "2026-06-12"},
            {"id": "mid", "mtime": 100.0, "date": "2026-06-10"},
            {"id": "old", "mtime": 50.0, "date": "2026-06-01"},
        ]
        ordered = pc.order_for_distill(rows)
        self.assertEqual([r["id"] for r in ordered], ["old", "mid", "new"])

    def test_filter_by_slugs_exact_match(self) -> None:
        rows = [
            {
                "project": "example-app",
                "workspace": "Users-alice-Work-example-app",
            },
            {
                "project": "other-app",
                "workspace": "Users-alice-Work-other-app",
            },
        ]
        filtered = pc.filter_by_slugs(rows, {"xamp"})
        self.assertEqual(len(filtered), 0)
        filtered = pc.filter_by_slugs(rows, {"example-app"})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["project"], "example-app")

    def test_needs_distill_after_same_day_distill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "a.jsonl"
            jsonl.write_text("{}\n", encoding="utf-8")
            distilled = datetime.now().replace(hour=8).strftime("%Y-%m-%dT%H:%M:%S")
            manifest = {
                "processed": [{"id": "a", "distilled_at": distilled}],
                "pending": [],
            }
            import time

            time.sleep(0.05)
            jsonl.write_text("{}\n{}\n", encoding="utf-8")
            self.assertTrue(pc.needs_distill("a", jsonl, manifest))

    def test_scan_chat_stats_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            stats = pc.scan_chat_stats(hub, projects_root=hub)
            self.assertEqual(stats["status"], "ok")
            self.assertIn("total_chats", stats)
            self.assertIn("active_90d", stats)
            self.assertIn("pending_180d", stats)
            self.assertIn("message", stats)


if __name__ == "__main__":
    unittest.main()
