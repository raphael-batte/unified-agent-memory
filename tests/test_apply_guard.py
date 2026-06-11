"""Tests for scripts/lib/apply_guard.py and distill-merge apply guard."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from helpers import load_script_module, minimal_hub

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import apply_guard as ag  # noqa: E402

dm = load_script_module("distill_merge", "distill-merge.py")


class TestApplyGuard(unittest.TestCase):
    def _hub_with_project(
        self,
        tmp: str,
        *,
        decisions: str,
        distilled_at: str,
        chat_id: str = "chat-abc-123",
    ) -> Path:
        hub = Path(tmp)
        minimal_hub(hub)
        project = hub / "chats" / "projects" / "app.md"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_text(
            f"# app\n_Last updated: {distilled_at}_\n\n"
            f"## Decisions\n\n{decisions}\n\n## Recent\n\n",
            encoding="utf-8",
        )
        manifest_path = hub / "chats" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["processed"] = [
            {
                "id": chat_id,
                "workspace": "Users-me-Work-app",
                "date": distilled_at[:10],
                "distilled_at": distilled_at,
                "distilled_to": ["projects/app.md"],
                "summary": "test",
            }
        ]
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return hub

    def test_curated_decisions_only_bootstrap_not_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = self._hub_with_project(
                tmp,
                decisions="- [bootstrap] decided to use docker for production deploy",
                distilled_at="2020-01-01T10:00:00",
            )
            project = hub / "chats" / "projects" / "app.md"
            self.assertEqual(ag.curated_decision_count(project), 0)

    def test_check_blocks_stale_curated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
            hub = self._hub_with_project(
                tmp,
                decisions="- Use staging before prod deploy",
                distilled_at=old,
            )
            manifest = json.loads(
                (hub / "chats" / "manifest.json").read_text(encoding="utf-8")
            )
            reason = ag.check_cli_apply_guard(
                hub,
                "chat-abc-123",
                hub / "chats" / "projects" / "app.md",
                manifest,
                max_age_days=7,
            )
            self.assertIsNotNone(reason)
            self.assertIn("curated", reason)

    def test_check_allows_fresh_curated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = datetime.now().isoformat(timespec="seconds")
            hub = self._hub_with_project(
                tmp,
                decisions="- Use staging before prod deploy",
                distilled_at=fresh,
            )
            manifest = json.loads(
                (hub / "chats" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(
                ag.check_cli_apply_guard(
                    hub,
                    "chat-abc-123",
                    hub / "chats" / "projects" / "app.md",
                    manifest,
                    max_age_days=7,
                )
            )

    def test_run_merge_blocks_apply_exit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
            hub = self._hub_with_project(
                tmp,
                decisions="- Curated deploy policy for production",
                distilled_at=old,
            )
            staging = hub / "chats" / "merge-staging" / "review-me.md"
            staging.parent.mkdir(parents=True, exist_ok=True)
            staging.write_text("KEEP THIS STAGING\n", encoding="utf-8")

            extract = {
                "uuid": "chat-abc-123",
                "workspace": "Users-me-Work-app",
                "workspace_slug": "app",
                "first_query": "q",
                "user_messages": ["msg"],
                "user_message_count": 1,
                "strategy": "tail",
                "keywords_hit": [],
                "date": datetime.now().strftime("%Y-%m-%d"),
            }
            result = dm.run_merge(
                memory_home=hub,
                chat_id="chat-abc-123",
                extract=extract,
                apply=True,
                force_apply=False,
            )
            self.assertEqual(result.get("status"), "blocked")
            self.assertEqual(staging.read_text(encoding="utf-8"), "KEEP THIS STAGING\n")

    def test_run_merge_force_apply_bypasses_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
            hub = self._hub_with_project(
                tmp,
                decisions="- Curated deploy policy for production",
                distilled_at=old,
            )
            extract = {
                "uuid": "chat-abc-123",
                "workspace": "Users-me-Work-app",
                "workspace_slug": "app",
                "first_query": "q",
                "user_messages": ["msg"],
                "user_message_count": 1,
                "strategy": "tail",
                "keywords_hit": [],
                "date": datetime.now().strftime("%Y-%m-%d"),
            }
            result = dm.run_merge(
                memory_home=hub,
                chat_id="chat-abc-123",
                extract=extract,
                apply=True,
                force_apply=True,
            )
            self.assertTrue(result.get("applied"))
            self.assertNotEqual(result.get("status"), "blocked")

    def test_bootstrap_only_apply_not_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
            hub = self._hub_with_project(
                tmp,
                decisions="- [bootstrap] decided to use docker for production deploy",
                distilled_at=old,
            )
            extract = {
                "uuid": "chat-abc-123",
                "workspace": "Users-me-Work-app",
                "workspace_slug": "app",
                "first_query": "q",
                "user_messages": ["msg"],
                "user_message_count": 1,
                "strategy": "tail",
                "keywords_hit": ["deploy"],
                "date": datetime.now().strftime("%Y-%m-%d"),
            }
            result = dm.run_merge(
                memory_home=hub,
                chat_id="chat-abc-123",
                extract=extract,
                apply=True,
                force_apply=False,
            )
            self.assertNotEqual(result.get("status"), "blocked")
            self.assertTrue(result.get("applied"))


if __name__ == "__main__":
    unittest.main()
