"""Tests for scripts/lib/hooks_config.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import hooks_config as hc  # noqa: E402


class TestHooksConfig(unittest.TestCase):
    def test_merge_adds_all_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hooks.json"
            result = hc.merge_hooks_file(path, dry_run=False)
            data = json.loads(path.read_text())
            hooks = data["hooks"]
            self.assertIn("sessionStart", hooks)
            self.assertIn("preCompact", hooks)
            self.assertIn("sessionEnd", hooks)
            self.assertIn("afterFileEdit", hooks)
            session_cmds = [
                e["command"] for e in hooks["sessionEnd"] if isinstance(e, dict)
            ]
            self.assertIn("./hooks/agent-memory-boundary.sh", session_cmds)
            self.assertIn("./hooks/agent-memory-session-end.sh", session_cmds)
            self.assertGreaterEqual(len(result["added"]), 4)

    def test_merge_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hooks.json"
            hc.merge_hooks_file(path, dry_run=False)
            second = hc.merge_hooks_file(path, dry_run=False)
            self.assertEqual(second["added"], [])


if __name__ == "__main__":
    unittest.main()
