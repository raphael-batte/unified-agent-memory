"""Tests for [auto] Open threads draft pipeline (v0.26)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import open_thread_draft as otd  # noqa: E402
from lib import pointer_curation_queue as pcq  # noqa: E402
from lib import project_merge as pm  # noqa: E402

_D = "2026-07-12"


def _labels(bullets: list[str]) -> list[str]:
    return [pm.open_thread_label(b) for b in bullets]


class TestUpsertOpenThreadTiered(unittest.TestCase):
    def test_auto_does_not_overwrite_curated(self) -> None:
        existing = ["**[sdm-ui]** deploy OK on test · _upd 2026-07-11_"]
        out, changed, reason = pm.upsert_open_thread_tiered(
            existing, "sdm-ui", "new auto text", updated=_D, tier=pm.TIER_AUTO
        )
        self.assertFalse(changed)
        self.assertEqual(reason, "skipped_curated")
        self.assertEqual(out, existing)

    def test_auto_replaces_auto_same_label(self) -> None:
        existing = ["**[sdm-ui]** [auto] old draft · _upd 2026-07-11_"]
        out, changed, _ = pm.upsert_open_thread_tiered(
            existing, "sdm-ui", "fresh draft", updated=_D, tier=pm.TIER_AUTO
        )
        self.assertTrue(changed)
        self.assertIn("[auto] fresh draft", out[0])
        self.assertEqual(pm.open_thread_tier(out[0]), pm.TIER_AUTO)

    def test_cap_evicts_auto_before_curated(self) -> None:
        curated = [
            f"**[c{i}]** curated {i} · _upd 2026-07-0{i}_" for i in range(1, 8)
        ]
        auto = ["**[a0]** [auto] old · _upd 2026-07-01_"]
        seed = curated + auto
        out, changed, _ = pm.upsert_open_thread_tiered(
            seed, "a1", "new auto", updated=_D, tier=pm.TIER_AUTO, cap=7
        )
        self.assertTrue(changed)
        self.assertEqual(len(out), 7)
        self.assertNotIn("a0", _labels(out))
        self.assertIn("a1", _labels(out))
        self.assertNotIn("c1", _labels(out))

    def test_cap_curated_full_skips_new_auto_label(self) -> None:
        curated = [
            f"**[c{i}]** curated {i} · _upd 2026-07-0{i}_" for i in range(7)
        ]
        out, changed, reason = pm.upsert_open_thread_tiered(
            curated, "new-dir", "draft", updated=_D, tier=pm.TIER_AUTO, cap=7
        )
        self.assertFalse(changed)
        self.assertEqual(reason, "skipped_cap_curated_full")


class TestDirectionLabel(unittest.TestCase):
    def test_path_first(self) -> None:
        extract = {
            "user_messages": ["see work/sdm/ui2026 - packages card on mobile"],
            "workspace_slug": "Trendymen",
            "first_query": "generic",
        }
        label = otd.infer_direction_label(extract, {"preview": "generic preview"})
        self.assertEqual(label, "sdm-ui2026")

    def test_preview_slug_fallback(self) -> None:
        extract = {
            "user_messages": ["short"],
            "workspace_slug": "Trendymen",
            "first_query": "deploy footer accordion on mobile test server",
        }
        label = otd.infer_direction_label(extract, None)
        self.assertTrue(label)
        self.assertIn("deploy", label)


class TestDraftPipeline(unittest.TestCase):
    def test_usable_segment_skips_junk_tail(self) -> None:
        extract = {
            "topic_segments": [
                {"segment": 1, "preview": "work/sdm footer deploy smoke pending on test"},
                {
                    "segment": 2,
                    "preview": "<mcp_meta_tools> You have access to MCP tools through GetMcpTools",
                },
            ],
            "user_messages": ["short"],
            "first_query": "x",
        }
        seg = otd.usable_topic_segment(extract)
        self.assertEqual(seg["segment"], 1)

    def test_single_tail_segment_only(self) -> None:
        extract = {
            "date": "2026-07-12",
            "user_messages": [
                "segment one topic",
                "work/sdm/ui2026 footer deploy smoke pending on test",
            ],
            "first_query": "segment one topic",
            "topic_segments": [
                {
                    "segment": 1,
                    "preview": "segment one topic about something else",
                    "start": 0,
                    "end": 1,
                },
                {
                    "segment": 2,
                    "preview": "work/sdm/ui2026 footer deploy smoke pending on test",
                    "start": 1,
                    "end": 2,
                },
            ],
        }
        seg = otd.tail_topic_segment(extract)
        self.assertEqual(seg["segment"], 2)
        label = otd.infer_direction_label(extract, seg)
        self.assertEqual(label, "sdm-ui2026")

    def test_draft_writes_auto_bullet(self) -> None:
        extract = {
            "date": "2026-07-12",
            "user_messages": [
                "work/sdm/ui2026 - footer deploy smoke pending on test server"
            ],
            "first_query": "work/sdm/ui2026",
            "workspace_slug": "Trendymen",
            "topic_segments": [
                {
                    "segment": 1,
                    "preview": "work/sdm/ui2026 - footer deploy smoke pending on test",
                    "start": 0,
                    "end": 1,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Trendymen.md"
            path.write_text(
                "# Trendymen\n\n## Open threads\n\n\n## Recent\n\n",
                encoding="utf-8",
            )
            result = otd.draft_open_threads_after_apply(path, extract)
            self.assertTrue(result["drafted"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("[auto]", text)
            self.assertIn("sdm-ui2026", text)

    def test_apply_extract_still_untouched(self) -> None:
        extract = {
            "uuid": "x",
            "workspace_slug": "app",
            "first_query": "work/sdm/ui2026 footer deploy smoke pending",
            "user_messages": ["work/sdm/ui2026 footer deploy smoke pending"],
            "user_message_count": 1,
            "topic_segments": [
                {
                    "segment": 1,
                    "preview": "work/sdm/ui2026 footer deploy smoke pending",
                    "start": 0,
                    "end": 1,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            path.write_text("# app\n\n## Open threads\n\n\n", encoding="utf-8")
            pm.apply_extract_to_project(path, extract, today=_D)
            _preamble, sections = pm._parse_sections(path.read_text(encoding="utf-8"))
            self.assertEqual(pm._bullets(sections.get("Open threads", "")), [])


class TestNeedsEnqueueOpenThread(unittest.TestCase):
    def test_enqueue_on_auto_draft(self) -> None:
        draft = {"drafted": True, "needs_curation": True}
        self.assertEqual(
            pcq.needs_enqueue({}, draft_result=draft),
            (True, "open-thread-draft"),
        )

    def test_skip_when_no_draft(self) -> None:
        self.assertEqual(pcq.needs_enqueue(None), (False, ""))


if __name__ == "__main__":
    unittest.main()
