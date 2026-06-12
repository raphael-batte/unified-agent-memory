"""Tests for scripts/lib/hub_search.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.hub_search import search_hub, tokenize  # noqa: E402
from lib.search_lang import expand_query_tokens  # noqa: E402


class TestHubSearch(unittest.TestCase):
    def test_tokenize_drops_stopwords(self) -> None:
        toks = tokenize("deploy the docker ssl fix")
        self.assertIn("depl", toks)
        self.assertNotIn("the", toks)

    def test_query_expansion(self) -> None:
        groups = [["prod", "production", "staging"]]
        expanded = expand_query_tokens(["prod"], groups)
        self.assertIn("prod", expanded)
        self.assertIn("stag", expanded)

    def test_search_decisions_ranked_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(
                "_Last updated: 2026-06-01_\n\n"
                "## Recent\n\n- unrelated nginx tweak\n\n"
                "## Decisions\n\n- Use docker ssl on prod deploy\n\n"
                "## Next step\n\n- Run smoke tests\n",
                encoding="utf-8",
            )
            result = search_hub(hub, "docker ssl prod", top=3, log_metrics=False)
            hits = result["hits"]
            self.assertGreaterEqual(len(hits), 1)
            self.assertIn("Decisions", hits[0]["section"])

    def test_deep_respects_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            extracts = hub / "chats" / "extracts"
            extracts.mkdir(parents=True)
            old = extracts / "old-chat.json"
            old.write_text(
                json.dumps(
                    {
                        "uuid": "old-chat-uuid-0001",
                        "first_query": "ancient deploy prod ssl",
                        "user_messages": ["ancient deploy prod ssl detail"],
                    }
                ),
                encoding="utf-8",
            )
            old_time = datetime.now() - timedelta(days=40)
            import os

            os.utime(old, (old_time.timestamp(), old_time.timestamp()))

            new = extracts / "new-chat.json"
            new.write_text(
                json.dumps(
                    {
                        "uuid": "new-chat-uuid-0002",
                        "first_query": "fresh deploy prod ssl",
                        "user_messages": ["fresh deploy prod ssl detail"],
                    }
                ),
                encoding="utf-8",
            )

            result = search_hub(
                hub, "deploy ssl", deep=True, retention_days=30, log_metrics=False
            )
            self.assertGreaterEqual(result["meta"].get("extracts_purged_by_retention", 0), 1)
            texts = " ".join(h["text"] for h in result["hits"])
            self.assertIn("fresh", texts)
            self.assertNotIn("ancient", texts)

    def test_search_corpus_dedupes_identical_archive_bullets(self) -> None:
        bullet = "canonical shareurl main_head sitemap deploy unique phrase"
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            archive = hub / "chats" / "archive" / "app-decisions.md"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(
                "# Archived decisions — app\n\n## Decisions\n\n"
                f"- {bullet}\n- {bullet}\n- {bullet}\n",
                encoding="utf-8",
            )
            from lib.hub_search import build_corpus

            docs, meta = build_corpus(hub, layers={"chats"})
            archive_docs = [d for d in docs if "archive" in d.rel_path]
            self.assertEqual(len(archive_docs), 1)
            result = search_hub(
                hub, "canonical shareurl main_head", top=5, log_metrics=False
            )
            archive_hits = [h for h in result["hits"] if "archive" in h["path"]]
            self.assertEqual(len(archive_hits), 1)

    def test_legacy_archive_without_section_header_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            archive = hub / "chats" / "archive" / "app-decisions.md"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(
                "# Archived decisions — app\n\n"
                "- canonical shareurl main_head sitemap slash deploy\n",
                encoding="utf-8",
            )
            result = search_hub(
                hub, "canonical shareurl sitemap", top=3, log_metrics=False
            )
            self.assertGreaterEqual(len(result["hits"]), 1)
            self.assertIn("archive", result["hits"][0]["path"])

    def test_archive_decisions_indexed_below_active(self) -> None:
        bullet = "Use canonical shareurl from server for main_head template deploy"
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(
                f"## Decisions\n\n- {bullet}\n",
                encoding="utf-8",
            )
            archive = hub / "chats" / "archive" / "app-decisions.md"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(
                f"# Archived decisions — app\n\n## Decisions\n\n- {bullet}\n",
                encoding="utf-8",
            )
            result = search_hub(
                hub, "canonical shareurl main_head", top=5, log_metrics=False
            )
            hits = result["hits"]
            self.assertGreaterEqual(len(hits), 2)
            paths = [h["path"] for h in hits]
            self.assertTrue(any("archive" in p for p in paths))
            self.assertTrue(any("projects" in p for p in paths))
            active = next(h for h in hits if "projects" in h["path"])
            archived = next(h for h in hits if "archive" in h["path"])
            self.assertGreater(active["score"], archived["score"])

    def test_context_paragraph_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            conv = hub / "context" / "conventions.md"
            conv.parent.mkdir(parents=True, exist_ok=True)
            conv.write_text(
                "_Last updated: 2026-06-05_\n\n"
                "## Deploy policy\n\n"
                "Always run smoke tests before production deploy.\n",
                encoding="utf-8",
            )
            result = search_hub(hub, "smoke production", top=5, log_metrics=False)
            self.assertTrue(any(h["layer"] == "context" for h in result["hits"]))


if __name__ == "__main__":
    unittest.main()
