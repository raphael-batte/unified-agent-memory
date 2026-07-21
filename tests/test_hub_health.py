"""Tests for scripts/lib/hub_health.py"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.hub_health import analyze_open_threads_coverage  # noqa: E402


def _thread(label: str, text: str, when: datetime | None) -> str:
    stamp = f" · _upd {when:%Y-%m-%d}_" if when else ""
    return f"- **[{label}]** {text}{stamp}\n"


class TestOpenThreadsCoverage(unittest.TestCase):
    def _hub(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        projects = Path(tmp.name) / "chats" / "projects"
        projects.mkdir(parents=True)
        for name, body in files.items():
            (projects / name).write_text(body, encoding="utf-8")
        return Path(tmp.name)

    def test_counts_projects_not_bullets(self) -> None:
        """Coverage answers 'does this project have a forward pointer', so two
        threads in one file must not outvote a project that has none."""
        now = datetime.now()
        hub = self._hub(
            {
                "app.md": "## Open threads\n\n"
                + _thread("deploy", "finish rollout", now)
                + _thread("api", "version the schema", now),
                "lib.md": "## Open threads\n\n",
            }
        )
        data = analyze_open_threads_coverage(hub)
        self.assertEqual(data["projects_scanned"], 2)
        self.assertEqual(data["projects_covered"], 1)
        self.assertEqual(data["threads_total"], 2)
        self.assertEqual(data["threads_coverage_rate"], 0.5)

    def test_example_is_not_scanned(self) -> None:
        """example.md ships with the framework — counting it would report
        coverage the user never earned."""
        hub = self._hub(
            {
                "app.md": "## Open threads\n\n"
                + _thread("deploy", "finish rollout", datetime.now()),
                "example.md": "## Open threads\n\n" + _thread("x", "sample", None),
            }
        )
        data = analyze_open_threads_coverage(hub)
        self.assertEqual(data["projects_scanned"], 1)
        self.assertEqual(data["threads_coverage_rate"], 1.0)

    def test_stale_project_counts_as_covered_but_not_fresh(self) -> None:
        old = datetime.now() - timedelta(days=90)
        hub = self._hub(
            {"app.md": "## Open threads\n\n" + _thread("deploy", "old work", old)}
        )
        data = analyze_open_threads_coverage(hub, days=30)
        self.assertEqual(data["projects_covered"], 1)
        self.assertEqual(data["projects_fresh"], 0)

    def test_empty_hub_reports_none_not_zero(self) -> None:
        """No projects means no opinion — a 0% would read as a failing hub."""
        data = analyze_open_threads_coverage(Path(tempfile.mkdtemp()))
        self.assertIsNone(data["threads_coverage_rate"])
        self.assertEqual(data["projects_scanned"], 0)


if __name__ == "__main__":
    unittest.main()
