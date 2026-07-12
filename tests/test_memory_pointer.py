"""Tests for scripts/memory-pointer.py (forward pointer = Open threads)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from helpers import load_script_module, minimal_hub

mp = load_script_module("memory_pointer", "memory-pointer.py")


class TestMemoryPointer(unittest.TestCase):
    def test_add_thread_writes_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=0)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            result = mp.add_open_thread(
                project,
                "sdm-ui",
                "Smoke footer on test",
                memory_home=hub,
            )
            text = project.read_text(encoding="utf-8")
            self.assertEqual(result["count"], 1)
            self.assertIn("## Open threads", text)
            self.assertIn("**[sdm-ui]** Smoke footer on test", text)

    def test_show_lists_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "app.md"
            mp.add_open_thread(project, "qa", "Run smoke tests", memory_home=None)
            threads = mp.read_open_threads(project)
            self.assertEqual(len(threads), 1)
            self.assertIn("**[qa]**", threads[0])


if __name__ == "__main__":
    unittest.main()
