"""Tests for scripts/lib/project_merge.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import project_merge as pm  # noqa: E402


class TestProjectMerge(unittest.TestCase):
    def test_apply_updates_recent_not_decisions(self) -> None:
        extract = {
            "uuid": "abcd-1234",
            "workspace_slug": "app",
            "first_query": "First query text",
            "user_messages": ["Raw user message not a decision"],
            "user_message_count": 2,
            "strategy": "tail",
            "keywords_hit": ["deploy"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text(
                "# app\n_Last updated: 2020-01-01_\n\n"
                "## Decisions\n\n- Curated only\n\n"
                "## Recent\n\n- old1\n- old2\n- old3\n- old4\n",
                encoding="utf-8",
            )
            result = pm.apply_extract_to_project(path, extract, today="2026-06-06")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(result["decisions_added"], 0)
            self.assertNotIn("Raw user message", text)
            self.assertNotIn("First query text", text)
            self.assertIn("Curated only", text)
            self.assertIn("2026-06-06", text)
            recent = pm._bullets(pm._parse_sections(text)[1].get("Recent", ""))
            self.assertLessEqual(len(recent), 3)

    def test_bootstrap_decisions_when_empty(self) -> None:
        extract = {
            "uuid": "x",
            "workspace_slug": "app",
            "first_query": "q",
            "user_messages": [
                "We decided to use docker for production deploy on the main server",
                "short",
            ],
            "user_message_count": 2,
            "strategy": "tail",
            "keywords_hit": ["deploy", "docker", "prod"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text(
                "# app\n\n## Decisions\n\n\n## Recent\n\n",
                encoding="utf-8",
            )
            result = pm.apply_extract_to_project(
                path, extract, today="2026-06-07", bootstrap_decisions=True
            )
            text = path.read_text(encoding="utf-8")
            self.assertEqual(result["decisions_added"], 1)
            self.assertIn("[bootstrap]", text)
            self.assertIn("docker", text)

    def test_bootstrap_skips_when_decisions_exist(self) -> None:
        extract = {
            "uuid": "x",
            "workspace_slug": "app",
            "user_messages": ["decided to deploy with docker on production"],
            "user_message_count": 1,
            "strategy": "tail",
            "keywords_hit": ["deploy"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text("## Decisions\n\n- Curated\n\n## Recent\n\n", encoding="utf-8")
            result = pm.apply_extract_to_project(
                path, extract, bootstrap_decisions=True
            )
            self.assertEqual(result["decisions_added"], 0)
            self.assertNotIn("[bootstrap]", path.read_text(encoding="utf-8"))

    def test_apply_sets_next_step_from_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "c.jsonl"
            jsonl.write_text(
                '{"role":"assistant","message":{"content":[{"type":"text",'
                '"text":"Done.\\n\\nNext step: run device QA script"}]}}\n',
                encoding="utf-8",
            )
            extract = {
                "uuid": "x",
                "workspace_slug": "app",
                "user_messages": [],
                "user_message_count": 0,
                "strategy": "tail",
                "source_path": str(jsonl),
            }
            path = Path(tmp) / "app.md"
            path.write_text("## Next step\n\n\n## Recent\n\n", encoding="utf-8")
            pm.apply_extract_to_project(path, extract, today="2026-06-07")
            self.assertIn("device QA", path.read_text(encoding="utf-8"))

    def test_apply_writes_no_pointer_placeholder(self) -> None:
        extract = {
            "uuid": "abcd-1234-uuid-full",
            "workspace_slug": "app",
            "first_query": "short",
            "user_messages": ["hi"],
            "user_message_count": 1,
            "strategy": "tail",
            "transcript_available": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text("## Next step\n\n\n## Recent\n\n", encoding="utf-8")
            result = pm.apply_extract_to_project(path, extract, today="2026-06-07")
            text = path.read_text(encoding="utf-8")
            self.assertTrue(result["next_step_placeholder"])
            self.assertEqual(result["next_step_kind"], "placeholder_empty")
            self.assertIn("_No forward pointer._", text)
            self.assertIn("abcd-123", text)

    def test_apply_writes_stale_placeholder(self) -> None:
        extract = {
            "uuid": "stale-uuid-1234",
            "workspace_slug": "app",
            "first_query": "q",
            "user_messages": ["ok"],
            "user_message_count": 1,
            "strategy": "tail",
            "transcript_available": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text(
                "## Next step\n\n- Deploy to production after SSL fix\n\n## Recent\n\n",
                encoding="utf-8",
            )
            result = pm.apply_extract_to_project(path, extract, today="2026-06-07")
            text = path.read_text(encoding="utf-8")
            self.assertTrue(result["next_step_placeholder"])
            self.assertEqual(result["next_step_kind"], "placeholder_stale")
            self.assertIn("[?]", text)
            self.assertIn("Deploy to production", text)

    def test_curated_next_step_preserved_on_weak_auto(self) -> None:
        extract = {
            "uuid": "new-chat-uuid",
            "workspace_slug": "app",
            "user_messages": ["hi"],
            "user_message_count": 1,
            "strategy": "tail",
            "watermark_user_count": 1,
            "watermark_tail_hash": "abc",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text(
                "## Next step\n\n- [curated] Run full smoke suite before release\n\n"
                "## Recent\n\n- [old](aaaa-bbbb-cccc-dddd-eeee-ffff-0000) 2026-06-01\n",
                encoding="utf-8",
            )
            result = pm.apply_extract_to_project(
                path,
                extract,
                today="2026-06-08",
                manifest_entry={
                    "watermark_user_count": 1,
                    "watermark_tail_hash": "abc",
                },
            )
            text = path.read_text(encoding="utf-8")
            self.assertTrue(result["pointer_preserved_curated"])
            self.assertIn("[curated]", text)
            self.assertIn("smoke suite", text)

    def test_curated_overwritten_by_live_signal_and_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "c.jsonl"
            jsonl.write_text(
                '{"role":"user","message":{"content":[{"type":"text",'
                '"text":"<user_query>okay then deploy security patch to staging</user_query>"}]}}\n',
                encoding="utf-8",
            )
            extract = {
                "uuid": "x",
                "workspace_slug": "app",
                "user_messages": [],
                "user_message_count": 5,
                "strategy": "tail",
                "source_path": str(jsonl),
                "watermark_user_count": 5,
                "watermark_tail_hash": "newhash",
            }
            path = Path(tmp) / "app.md"
            path.write_text(
                "## Next step\n\n- [curated] Old curated step here for test\n\n## Recent\n\n",
                encoding="utf-8",
            )
            result = pm.apply_extract_to_project(
                path,
                extract,
                today="2026-06-08",
                manifest_entry={
                    "watermark_user_count": 1,
                    "watermark_tail_hash": "oldhash",
                },
            )
            text = path.read_text(encoding="utf-8")
            self.assertFalse(result["pointer_preserved_curated"])
            self.assertEqual(result["next_step_kind"], "extracted")
            self.assertIn("security patch", text)
            self.assertNotIn("[curated]", text)

    def test_apply_writes_summary_bullets_when_empty(self) -> None:
        extract = {
            "uuid": "x",
            "workspace_slug": "app",
            "summary_bullets": ["Topic A polishing", "Topic B deploy"],
            "user_messages": [],
            "user_message_count": 100,
            "strategy": "importance",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text("## Summary\n\n\n## Recent\n\n", encoding="utf-8")
            pm.apply_extract_to_project(path, extract, today="2026-06-08")
            text = path.read_text(encoding="utf-8")
            self.assertIn("Topic A polishing", text)
            self.assertIn("Topic B deploy", text)

    def test_merge_extracted_decisions_appends_novel(self) -> None:
        extract = {
            "uuid": "x",
            "workspace_slug": "app",
            "user_messages": [],
            "user_message_count": 10,
            "strategy": "importance",
            "decision_candidates": [
                {"text": "folder is named home not landing", "source": "commitment"},
            ],
            "decisions_extracted": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text(
                "## Decisions\n\n- Curated deploy policy\n\n## Recent\n\n",
                encoding="utf-8",
            )
            result = pm.apply_extract_to_project(path, extract, today="2026-06-08")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(result["decisions_merged"], 1)
            self.assertIn("[extracted]", text)
            self.assertIn("home", text)
            self.assertIn("Curated deploy policy", text)

    def test_enforce_extracted_cap_archives_oldest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            bullets = [f"[extracted] decision number {i}" for i in range(35)]
            bullets.insert(0, "- [curated] Keep this policy")
            trimmed, evicted = pm.enforce_extracted_decisions_cap(
                bullets,
                max_extracted=30,
                memory_home=hub,
                slug="irm",
            )
            extracted = [b for b in trimmed if b.startswith("[extracted]")]
            self.assertEqual(len(extracted), 30)
            self.assertEqual(evicted, 5)
            self.assertTrue(any("[curated]" in b for b in trimmed))
            archive = hub / "chats" / "archive" / "irm-decisions.md"
            self.assertTrue(archive.is_file())
            self.assertIn("decision number 0", archive.read_text(encoding="utf-8"))

    def test_merge_at_cap_appends_then_evicts_to_archive(self) -> None:
        existing = [f"[extracted] old decision {i}" for i in range(30)]
        existing.insert(0, "[curated] Keep this policy")
        extract = {
            "workspace_slug": "app",
            "decision_candidates": [
                {"text": "new decision alpha one two three four"},
                {"text": "new decision beta one two three four five"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            merged, added = pm.merge_extracted_decisions(
                existing,
                extract,
                max_add=6,
                max_extracted=30,
                memory_home=hub,
                slug="app",
            )
            extracted = [b for b in merged if b.startswith("[extracted]")]
            self.assertEqual(added, 2)
            self.assertEqual(len(extracted), 30)
            self.assertIn("[curated] Keep this policy", merged)
            self.assertTrue(
                any("new decision alpha" in b for b in extracted),
                "newest candidates should remain after cap",
            )
            archive = hub / "chats" / "archive" / "app-decisions.md"
            self.assertTrue(archive.is_file())
            self.assertIn("old decision 0", archive.read_text(encoding="utf-8"))
            self.assertIn("old decision 1", archive.read_text(encoding="utf-8"))

    def test_archive_has_decisions_section_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            pm.archive_evicted_decisions(
                hub,
                "app",
                ["[extracted] canonical URL must use shareurl from server"],
            )
            path = hub / "chats" / "archive" / "app-decisions.md"
            text = path.read_text(encoding="utf-8")
            self.assertIn("## Decisions", text)
            sections = pm._parse_sections(text)[1]
            bullets = pm._bullets(sections.get("Decisions", ""))
            self.assertEqual(len(bullets), 1)
            self.assertIn("shareurl", bullets[0])

    def test_archive_legacy_format_upgraded_on_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            archive = hub / "chats" / "archive" / "app-decisions.md"
            archive.parent.mkdir(parents=True)
            archive.write_text(
                "# Archived decisions — app\n\n"
                "- [extracted] legacy bullet without section header\n",
                encoding="utf-8",
            )
            pm.archive_evicted_decisions(
                hub, "app", ["[extracted] new bullet after legacy upgrade"]
            )
            text = archive.read_text(encoding="utf-8")
            self.assertIn("## Decisions", text)
            bullets = pm._bullets(pm._parse_sections(text)[1].get("Decisions", ""))
            self.assertEqual(len(bullets), 2)
            self.assertIn("legacy bullet", bullets[0])
            self.assertIn("new bullet", bullets[1])

    def test_archive_two_batches_keep_distinct_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            pm.archive_evicted_decisions(hub, "app", ["[extracted] first batch"])
            pm.archive_evicted_decisions(hub, "app", ["[extracted] second batch"])
            text = (hub / "chats" / "archive" / "app-decisions.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("## Decisions", text)
            bullets = pm._bullets(pm._parse_sections(text)[1].get("Decisions", ""))
            self.assertEqual(len(bullets), 2)

    def test_archive_skips_duplicate_evicted_bullets(self) -> None:
        bullet = "[extracted] canonical shareurl from server for main_head template"
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            n1 = pm.archive_evicted_decisions(hub, "app", [bullet])
            n2 = pm.archive_evicted_decisions(hub, "app", [bullet])
            self.assertEqual(n1, 1)
            self.assertEqual(n2, 0)
            bullets = pm._bullets(
                pm._parse_sections(
                    (hub / "chats" / "archive" / "app-decisions.md").read_text(
                        encoding="utf-8"
                    )
                )[1].get("Decisions", "")
            )
            self.assertEqual(len(bullets), 1)

    def test_compact_archive_removes_duplicate_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            archive = hub / "chats" / "archive" / "app-decisions.md"
            archive.parent.mkdir(parents=True)
            archive.write_text(
                "# Archived decisions — app\n\n## Decisions\n\n"
                "- [extracted] same decision text repeated here for test\n"
                "- [extracted] same decision text repeated here for test\n"
                "- [extracted] unique other decision text for test case\n",
                encoding="utf-8",
            )
            removed = pm.compact_archive_decisions(hub, "app")
            self.assertEqual(removed, 1)
            bullets = pm._bullets(
                pm._parse_sections(archive.read_text(encoding="utf-8"))[1].get(
                    "Decisions", ""
                )
            )
            self.assertEqual(len(bullets), 2)

    def test_archive_evicted_appends_not_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            pm.archive_evicted_decisions(
                hub, "app", ["[extracted] first batch evicted item here"]
            )
            pm.archive_evicted_decisions(
                hub, "app", ["[extracted] second batch evicted item here"]
            )
            text = (hub / "chats" / "archive" / "app-decisions.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("first batch", text)
            self.assertIn("second batch", text)

    def test_enforce_cap_on_read_without_new_decisions(self) -> None:
        extract = {
            "uuid": "cap-only",
            "workspace_slug": "irm",
            "first_query": "noop",
            "user_messages": [],
            "user_message_count": 1,
            "strategy": "tail",
            "keywords_hit": [],
            "decision_candidates": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            path = hub / "chats" / "projects" / "irm.md"
            path.parent.mkdir(parents=True)
            bullets = [f"- [extracted] stale decision {i}" for i in range(35)]
            path.write_text(
                "# irm\n_Last updated: 2020-01-01_\n\n"
                "## Decisions\n\n" + "\n".join(bullets) + "\n\n## Recent\n\n",
                encoding="utf-8",
            )
            pm.apply_extract_to_project(
                path,
                extract,
                today="2026-06-08",
                memory_home=hub,
            )
            text = path.read_text(encoding="utf-8")
            extracted = [
                b for b in pm._bullets(pm._parse_sections(text)[1].get("Decisions", ""))
                if b.startswith("[extracted]")
            ]
            self.assertEqual(len(extracted), 30)

    def test_apply_leaves_summary_empty(self) -> None:
        extract = {
            "uuid": "x",
            "workspace_slug": "newapp",
            "first_query": "What is the deploy process for production?",
            "user_messages": [],
            "user_message_count": 1,
            "strategy": "all",
            "keywords_hit": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "newapp.md"
            pm.apply_extract_to_project(path, extract, today="2026-06-06")
            text = path.read_text(encoding="utf-8")
            sections = pm._parse_sections(text)[1]
            self.assertEqual(sections.get("Summary", "").strip(), "")
            self.assertNotIn("deploy process", text)


if __name__ == "__main__":
    unittest.main()
