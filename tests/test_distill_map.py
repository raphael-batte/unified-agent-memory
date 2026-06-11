"""Tests for distill map-reduce helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import distill_map as dm  # noqa: E402


class TestDistillMap(unittest.TestCase):
    def test_parse_agent_map_bullets(self) -> None:
        md = """# Map staging
## Window 1 (10 user msgs)
## Map (agent fills)
- decided to use watermark instead of mtime
- deploy v0.10.2 next

## Window 2 (8 user msgs)
## Map (agent fills)
- run weekly-verify with notify
"""
        parsed = dm.parse_agent_map_bullets(md)
        self.assertEqual(len(parsed[1]), 2)
        self.assertIn("watermark", parsed[1][0])

    def test_run_reduce(self) -> None:
        extract = {"workspace_slug": "foo", "uuid": "abc-123"}
        md = """## Window 1 (1 user msgs)
## Map (agent fills)
- ship baseline alerts for metrics gap detection
"""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            map_path = hub / "map.md"
            map_path.write_text(md, encoding="utf-8")
            out = dm.run_reduce(hub, extract, map_path)
            self.assertTrue(out.is_file())
            text = out.read_text(encoding="utf-8")
            self.assertIn("baseline alerts", text)


if __name__ == "__main__":
    unittest.main()
