"""Tests for scripts/lib/hub_health.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.hub_health import analyze_project_pointers  # noqa: E402


class TestHubHealth(unittest.TestCase):
    def test_pointer_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            project = hub / "chats" / "projects"
            project.mkdir(parents=True)
            (project / "app.md").write_text(
                "## Next step\n\n- Run smoke tests\n- _No forward pointer._\n",
                encoding="utf-8",
            )
            data = analyze_project_pointers(hub)
            self.assertGreaterEqual(data["pointer_extracted"], 1)
            self.assertGreaterEqual(data["pointer_placeholder"], 1)


if __name__ == "__main__":
    unittest.main()
