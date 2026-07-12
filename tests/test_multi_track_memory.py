"""Multi-track Open threads: upsert semantics + independence from Next step."""

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


class TestUpsertOpenThreadPure(unittest.TestCase):
    def test_appends_new_direction(self) -> None:
        out = pm.upsert_open_thread(["**[a]** one"], "b", "two")
        self.assertEqual(out, ["**[a]** one", "**[b]** two"])

    def test_replaces_same_label_case_insensitive(self) -> None:
        out = pm.upsert_open_thread(["**[ACME]** old"], "acme", "new")
        self.assertEqual(out, ["**[acme]** new"])

    def test_two_directions_open_threads_independent(self) -> None:
        out = pm.upsert_open_thread(["**[a]** one"], "b", "two")
        out = pm.upsert_open_thread(out, "a", "one-updated")
        self.assertEqual(out, ["**[b]** two", "**[a]** one-updated"])

    def test_cap_evicts_oldest(self) -> None:
        seed = [f"**[d{i}]** t{i}" for i in range(7)]
        out = pm.upsert_open_thread(seed, "d7", "t7", cap=7)
        self.assertEqual(len(out), 7)
        self.assertNotIn("**[d0]** t0", out)
        self.assertIn("**[d7]** t7", out)

    def test_drops_empty_bullets(self) -> None:
        out = pm.upsert_open_thread(["", "  "], "a", "one")
        self.assertEqual(out, ["**[a]** one"])

    def test_empty_label_or_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            pm.upsert_open_thread([], "", "text")
        with self.assertRaises(ValueError):
            pm.upsert_open_thread([], "label", "")


class TestAddOpenThreadFile(unittest.TestCase):
    def test_creates_file_and_writes_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proj.md"
            result = memory_pointer.add_open_thread(path, "widget-ui", "check menu")
            self.assertEqual(result["count"], 1)
            text = path.read_text(encoding="utf-8")
            self.assertIn("## Open threads", text)
            self.assertIn("- **[widget-ui]** check menu", text)

    def test_next_step_weak_auto_does_not_clear_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            memory_pointer.add_open_thread(path, "widget-ui", "check menu")
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
            self.assertIn("**[widget-ui]** check menu", threads)
            self.assertIn("**[agent-mem]** multi-track", threads)


if __name__ == "__main__":
    unittest.main()
