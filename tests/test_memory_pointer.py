"""Tests for scripts/memory-pointer.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import load_script_module, minimal_hub

mp = load_script_module("memory_pointer", "memory-pointer.py")


class TestMemoryPointer(unittest.TestCase):
    def test_set_curated_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=0)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text("## Next step\n\n\n## Recent\n\n", encoding="utf-8")
            result = mp.set_curated_pointer(
                project,
                "Run smoke tests after fixture import",
                memory_home=hub,
            )
            text = project.read_text(encoding="utf-8")
            self.assertTrue(result["curated"])
            self.assertIn("[curated]", text)
            self.assertIn("smoke tests", text)

    def test_show_curated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            mp.set_curated_pointer(project, "Ship v0.15 pointer provenance", memory_home=None)
            pointer, curated = mp.read_pointer_bullet(project)
            self.assertTrue(curated)
            self.assertIn("v0.15", pointer or "")


if __name__ == "__main__":
    unittest.main()
