"""Tests for scripts/lib/workspace_slug_resolve.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import workspace_slug_resolve as wsr  # noqa: E402


class TestResolveWorkspaceSlug(unittest.TestCase):
    def test_distill_match_by_basename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            projects = hub / "chats" / "projects"
            projects.mkdir(parents=True)
            (projects / "my-app.md").write_text("# my-app\n", encoding="utf-8")
            ws = Path("/anywhere/my-app")
            slug, reason = wsr.resolve_slug(ws, memory_home=hub)
            self.assertEqual(slug, "my-app")
            self.assertEqual(reason, "distill_match")

    def test_only_distill_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            projects = hub / "chats" / "projects"
            projects.mkdir(parents=True)
            (projects / "solo-project.md").write_text("# solo\n", encoding="utf-8")
            ws = Path("/work/unrelated-name")
            slug, reason = wsr.resolve_slug(ws, memory_home=hub)
            self.assertEqual(slug, "solo-project")
            self.assertEqual(reason, "only_distill")

    def test_basename_fallback_when_no_distills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats" / "projects").mkdir(parents=True)
            ws = Path("/projects/new-repo")
            slug, reason = wsr.resolve_slug(ws, memory_home=hub)
            self.assertEqual(slug, "new-repo")
            self.assertEqual(reason, "basename_fallback")


if __name__ == "__main__":
    unittest.main()
