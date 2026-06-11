"""Tests for scripts/lib/global_context_bootstrap.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from helpers import minimal_hub

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import global_context_bootstrap as gcb  # noqa: E402


class TestGlobalContextBootstrap(unittest.TestCase):
    def test_merge_projects_table(self) -> None:
        text = """# Global Context

## Projects

| Project | Path / repo | Status | Details |
|---------|-------------|--------|---------|
| old-app | `~/old` | active | keep |

"""
        projects = {
            "new-app": {
                "slug": "new-app",
                "path": "/tmp/new-app",
                "summary": "First query",
                "status": "active",
            }
        }
        new_text, count = gcb.merge_projects_table(text, projects)
        self.assertEqual(count, 1)
        self.assertIn("new-app", new_text)
        self.assertIn("old-app", new_text)

    def test_collect_projects_keeps_latest_distilled_at(self) -> None:
        manifest = {
            "processed": [
                {
                    "id": "old",
                    "workspace": "Users-me-Work-demo",
                    "distilled_at": "2026-01-01T10:00:00",
                    "summary": "Old topic",
                },
                {
                    "id": "new",
                    "workspace": "Users-me-Work-demo",
                    "distilled_at": "2026-06-06T18:00:00",
                    "summary": "Latest topic",
                },
            ],
            "pending": [],
        }
        projects = gcb.collect_projects_from_manifest(manifest)
        self.assertEqual(projects["demo"]["summary"], "Latest topic")

    def test_repo_path_prefers_workspace_path(self) -> None:
        manifest = {
            "processed": [
                {
                    "id": "x",
                    "workspace": "encoded-folder",
                    "workspace_path": "/real/path/to/repo",
                    "distilled_at": "2026-06-06",
                    "summary": "Hi",
                }
            ],
            "pending": [],
        }
        projects = gcb.collect_projects_from_manifest(manifest)
        self.assertEqual(projects["folder"]["path"], "/real/path/to/repo")

    def test_bootstrap_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            manifest = {
                "processed": [
                    {
                        "id": "x",
                        "workspace": "Users-me-Work-demo",
                        "distilled_at": "2026-06-06",
                        "summary": "Demo chat",
                        "distilled_to": ["projects/demo.md"],
                    }
                ],
                "pending": [],
            }
            result = gcb.bootstrap_global_context(hub, manifest, dry_run=False)
            self.assertGreaterEqual(result["projects"], 1)
            gc = (hub / "context" / "GLOBAL_CONTEXT.md").read_text()
            self.assertIn("demo", gc)


if __name__ == "__main__":
    unittest.main()
