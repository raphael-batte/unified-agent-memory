"""Routing integration: search surfaces Open threads; fresh hub is generic."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.hub_search import search_hub  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class TestRoutingIntegration(unittest.TestCase):
    def test_search_finds_direction_in_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(
                "_Last updated: 2026-06-01_\n\n"
                "## Decisions\n\n- unrelated nginx tweak\n\n"
                "## Open threads\n\n"
                "- **[lang-learn]** Wire pre-distill cue mining for verbs\n\n"
                "## Recent\n\n- old\n",
                encoding="utf-8",
            )
            result = search_hub(hub, "cue mining verbs", top=5, log_metrics=False)
            hits = result["hits"]
            self.assertTrue(
                any("Open threads" in h["section"] for h in hits),
                msg=f"Open threads not surfaced: {[h['section'] for h in hits]}",
            )

    def test_new_user_hub_has_only_example_project(self) -> None:
        example = REPO / "templates" / "chats" / "projects" / "example.md"
        self.assertTrue(example.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "chats" / "projects"
            projects.mkdir(parents=True)
            shutil.copy(example, projects / "example.md")
            files = sorted(p.name for p in projects.glob("*.md"))
            self.assertEqual(files, ["example.md"])
            text = (projects / "example.md").read_text(encoding="utf-8")
            for banned in ("sdm", "trendymen", "steaklover"):
                self.assertNotIn(banned, text.lower())


if __name__ == "__main__":
    unittest.main()
