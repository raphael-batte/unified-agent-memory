"""Tests for scripts/distill-merge.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, load_script_module, minimal_hub

dm = load_script_module("distill_merge", "distill-merge.py")
de = load_script_module("distill_extract", "distill-extract.py")
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample-chat.jsonl"


class TestDistillMerge(unittest.TestCase):
    def test_build_staging_preserves_language(self) -> None:
        extract = {
            "uuid": "abc",
            "workspace_slug": "app",
            "first_query": "Deploy with manual approve",
            "user_messages": ["Deploy example-app to prod", "Entscheidung Migration DE"],
            "user_message_count": 2,
            "strategy": "all",
            "keywords_hit": ["deploy"],
        }
        md = dm.build_staging_markdown(extract, project_rel="projects/app.md")
        self.assertIn("Deploy example-app", md)
        self.assertIn("Entscheidung", md)
        self.assertIn("Raw candidates", md)
        self.assertIn("not Decisions", md)

    def test_staging_uses_final_summary(self) -> None:
        extract = {
            "uuid": "abc",
            "workspace_slug": "app",
            "first_query": "Initial deploy question",
            "final_summary": "Assistant wrapped up: run flutter test on device tonight.",
            "user_messages": ["deploy please"],
            "user_message_count": 1,
            "strategy": "tail",
            "keywords_hit": [],
        }
        md = dm.build_staging_markdown(extract, project_rel="projects/app.md")
        self.assertIn("flutter test on device", md)
        self.assertIn("### Initial request", md)
        self.assertIn("Initial deploy question", md)

    def test_staging_recent_has_chat_link(self) -> None:
        extract = {
            "uuid": "chat-uuid-full",
            "workspace_slug": "app",
            "first_query": "Deploy fix",
            "user_messages": ["msg"],
            "user_message_count": 1,
            "strategy": "tail",
            "keywords_hit": [],
            "transcript_available": True,
            "source_path": "/tmp/fake.jsonl",
        }
        md = dm.build_staging_markdown(extract, project_rel="projects/app.md")
        self.assertIn("[Deploy fix](chat-uuid-full)", md)

    def test_run_merge_updates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            extract = de.build_extract(
                FIXTURE,
                projects_root=FIXTURE.parent,
                strategy="all",
            )
            extract["workspace"] = "Users-me-Work-app1"
            extract["workspace_slug"] = "app1"
            result = dm.run_merge(
                memory_home=hub,
                chat_id="merge-test-uuid",
                extract=extract,
                dry_run=False,
            )
            self.assertFalse(result["dry_run"])
            manifest = json.loads((hub / "chats" / "manifest.json").read_text())
            ids = [e["id"] for e in manifest["processed"]]
            self.assertIn("merge-test-uuid", ids)
            staging = Path(result["staging_path"])
            self.assertTrue(staging.is_file())
            self.assertTrue((hub / "chats" / "extracts" / "merge-test-uuid.json").is_file())

    def test_run_merge_apply_recent_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            extract = {
                "uuid": "apply-uuid",
                "workspace": "Users-me-Work-app1",
                "workspace_slug": "app1",
                "date": "2026-06-06",
                "first_query": "Query",
                "user_messages": ["Raw message not for Decisions"],
                "user_message_count": 1,
                "strategy": "tail",
                "keywords_hit": [],
            }
            result = dm.run_merge(
                memory_home=hub,
                chat_id="apply-uuid",
                extract=extract,
                apply=True,
            )
            self.assertTrue(result["applied"])
            project = Path(result["project_file"])
            text = project.read_text(encoding="utf-8")
            self.assertTrue(project.is_file())
            self.assertIn("distilled from chat", text)
            self.assertNotIn("Raw message not for Decisions", text)

    def test_run_merge_uses_manifest_distilled_to(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            manifest = {
                "processed": [
                    {
                        "id": "chat-1",
                        "distilled_to": ["projects/other-app.md"],
                        "workspace": "Users-alice-Work-example-app",
                    }
                ],
                "pending": [],
            }
            (hub / "chats" / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            extract = {
                "uuid": "chat-1",
                "workspace": "Users-alice-Work-example-app",
                "workspace_slug": "example-app",
                "first_query": "q",
                "user_messages": [],
                "user_message_count": 0,
                "strategy": "tail",
            }
            result = dm.run_merge(memory_home=hub, chat_id="chat-1", extract=extract)
            self.assertEqual(result["project_rel"], "projects/other-app.md")
            self.assertTrue(
                str(result["project_file"]).endswith("chats/projects/other-app.md")
            )

    def test_run_merge_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub)
            extract = {"uuid": "x", "workspace_slug": "z", "first_query": "q", "user_messages": []}
            result = dm.run_merge(
                memory_home=hub,
                chat_id="dry-uuid",
                extract=extract,
                dry_run=True,
            )
            self.assertTrue(result["dry_run"])
            self.assertEqual(len(json.loads((hub / "chats" / "manifest.json").read_text())["processed"]), 1)


if __name__ == "__main__":
    unittest.main()
