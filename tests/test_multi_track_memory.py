"""Multi-track Open threads: upsert semantics + distill independence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import project_merge as pm  # noqa: E402
import importlib.util

_MP_PATH = SCRIPTS / "memory-pointer.py"
_spec = importlib.util.spec_from_file_location("memory_pointer_mod", _MP_PATH)
memory_pointer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(memory_pointer)


_D = "2026-07-12"


def _labels(bullets: list[str]) -> list[str]:
    return [pm.open_thread_label(b) for b in bullets]


class TestUpsertOpenThreadPure(unittest.TestCase):
    def test_appends_new_direction(self) -> None:
        out = pm.upsert_open_thread(["**[a]** one"], "b", "two", updated=_D)
        self.assertEqual(_labels(out), ["a", "b"])
        self.assertEqual(out[1], "**[b]** two · _upd 2026-07-12_")

    def test_replaces_same_label_case_insensitive(self) -> None:
        out = pm.upsert_open_thread(["**[SDM]** old"], "sdm", "new", updated=_D)
        self.assertEqual(out, ["**[sdm]** new · _upd 2026-07-12_"])

    def test_two_directions_open_threads_independent(self) -> None:
        out = pm.upsert_open_thread(["**[a]** one · _upd 2026-07-01_"], "b", "two", updated=_D)
        out = pm.upsert_open_thread(out, "a", "one-updated", updated=_D)
        self.assertEqual(_labels(out), ["b", "a"])

    def test_retouch_refreshes_timestamp(self) -> None:
        out = pm.upsert_open_thread(["**[a]** one · _upd 2026-06-01_"], "a", "one", updated=_D)
        self.assertEqual(pm.parse_open_thread(out[0])["updated"], _D)

    def test_cap_evicts_oldest(self) -> None:
        seed = [f"**[d{i}]** t{i} · _upd 2026-07-0{i}_" for i in range(7)]
        out = pm.upsert_open_thread(seed, "d7", "t7", updated=_D, cap=7)
        self.assertEqual(len(out), 7)
        self.assertNotIn("d0", _labels(out))
        self.assertIn("d7", _labels(out))

    def test_drops_empty_bullets(self) -> None:
        out = pm.upsert_open_thread(["", "  "], "a", "one", updated=_D)
        self.assertEqual(_labels(out), ["a"])

    def test_incoming_stamp_is_normalized_not_doubled(self) -> None:
        out = pm.upsert_open_thread([], "a", "one · _upd 2026-01-01_", updated=_D)
        self.assertEqual(out, ["**[a]** one · _upd 2026-07-12_"])

    def test_empty_label_or_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            pm.upsert_open_thread([], "", "text", updated=_D)
        with self.assertRaises(ValueError):
            pm.upsert_open_thread([], "label", "", updated=_D)


class TestParseOpenThread(unittest.TestCase):
    def test_parses_label_text_and_date(self) -> None:
        p = pm.parse_open_thread("**[seo]** defer head · _upd 2026-07-11_")
        self.assertEqual(p, {"label": "seo", "text": "defer head", "updated": "2026-07-11"})

    def test_undated_bullet_has_none_updated(self) -> None:
        p = pm.parse_open_thread("**[seo]** defer head")
        self.assertEqual(p["updated"], None)
        self.assertEqual(p["text"], "defer head")

    def test_non_thread_line_returns_none(self) -> None:
        self.assertIsNone(pm.parse_open_thread("- just a plain bullet"))


class TestAddOpenThreadFile(unittest.TestCase):
    def test_creates_file_and_writes_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proj.md"
            result = memory_pointer.add_open_thread(path, "sdm-ui", "check menu")
            self.assertEqual(result["count"], 1)
            text = path.read_text(encoding="utf-8")
            self.assertIn("## Open threads", text)
            self.assertIn("- **[sdm-ui]** check menu · _upd", text)

    def test_apply_extract_does_not_clear_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            memory_pointer.add_open_thread(path, "sdm-ui", "check menu")
            memory_pointer.add_open_thread(path, "agent-mem", "multi-track")
            extract = {
                "uuid": "bbbb-2222",
                "workspace_slug": "app",
                "first_query": "unrelated tail",
                "user_messages": ["noise"],
                "user_message_count": 1,
                "strategy": "tail",
            }
            pm.apply_extract_to_project(path, extract, today="2026-06-06")
            threads = memory_pointer.read_open_threads(path)
            labels = [pm.open_thread_label(b) for b in threads]
            self.assertIn("sdm-ui", labels)
            self.assertIn("agent-mem", labels)


if __name__ == "__main__":
    unittest.main()
