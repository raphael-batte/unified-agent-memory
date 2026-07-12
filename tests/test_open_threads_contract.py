"""Contract tests for ## Open threads: distill must never touch it.

These lock in behaviour that already holds in project_merge.apply_extract_to_project
(Open threads is passthrough) so future edits cannot silently regress multi-track state.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import project_merge as pm  # noqa: E402

_EXTRACT = {
    "uuid": "aaaa-1111",
    "workspace_slug": "app",
    "first_query": "First query text",
    "user_messages": ["Raw user message not a decision"],
    "user_message_count": 2,
    "strategy": "tail",
    "keywords_hit": ["deploy"],
}


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


class TestOpenThreadsContract(unittest.TestCase):
    def test_apply_extract_preserves_open_threads_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            _write(
                path,
                "# app\n_Last updated: 2020-01-01_\n\n"
                "## Decisions\n\n- [curated] keep me\n\n"
                "## Open threads\n\n"
                "- **[widget-ui]** Check mobile menu on test\n"
                "- **[agent-memory]** Multi-track state lives here\n\n"
                "## Recent\n\n- old1\n",
            )
            pm.apply_extract_to_project(path, _EXTRACT, today="2026-06-06")
            text = path.read_text(encoding="utf-8")
            self.assertIn("- **[widget-ui]** Check mobile menu on test", text)
            self.assertIn("- **[agent-memory]** Multi-track state lives here", text)

    def test_apply_extract_does_not_invent_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            _write(
                path,
                "# app\n_Last updated: 2020-01-01_\n\n"
                "## Decisions\n\n- [curated] keep\n\n"
                "## Open threads\n\n\n"
                "## Recent\n\n- old1\n",
            )
            pm.apply_extract_to_project(path, _EXTRACT, today="2026-06-06")
            _preamble, sections = pm._parse_sections(
                path.read_text(encoding="utf-8")
            )
            self.assertEqual(pm._bullets(sections.get("Open threads", "")), [])

    def test_curated_decisions_survive_new_extracted(self) -> None:
        extract = {
            **_EXTRACT,
            "decisions": ["Use rolling 30d retention for extracted bullets"],
            "decisions_extracted": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.md"
            _write(
                path,
                "# app\n_Last updated: 2020-01-01_\n\n"
                "## Decisions\n\n- [curated] **arch:** durable why\n\n"
                "## Open threads\n\n- **[x]** t\n\n"
                "## Recent\n\n- old1\n",
            )
            pm.apply_extract_to_project(path, extract, today="2026-06-06")
            text = path.read_text(encoding="utf-8")
            self.assertIn("- [curated] **arch:** durable why", text)


if __name__ == "__main__":
    unittest.main()
