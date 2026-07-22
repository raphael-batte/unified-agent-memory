"""An empty chat is a normal outcome, not a crash.

A transcript with no user turns raised TranscriptEmptyError straight out of
distill-merge, so a batch run died on the first empty chat and the manifest's
own "no_content" status could not be reached from the CLI.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT

UUID = "11111111-2222-3333-4444-555555555555"


class TestEmptyTranscriptExitsCleanly(unittest.TestCase):
    def _run(self, rows: str) -> subprocess.CompletedProcess:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "projects" / "ws"
        root.mkdir(parents=True)
        (root / f"{UUID}.jsonl").write_text(rows, encoding="utf-8")
        hub = Path(tmp.name) / "hub"
        (hub / "chats").mkdir(parents=True)
        return subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "distill-merge.py"),
                UUID,
                "--apply",
                "--memory-home",
                str(hub),
                "--projects-root",
                str(root.parent),
            ],
            capture_output=True,
            text=True,
        )

    def test_no_user_rows_exits_zero(self) -> None:
        result = self._run('{"role":"assistant","content":"hi"}\n')
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertIn("no_content", result.stdout)

    def test_no_traceback_is_printed(self) -> None:
        result = self._run('{"role":"assistant","content":"hi"}\n')
        self.assertNotIn("Traceback", result.stderr)

    def test_only_noise_user_rows_exits_zero(self) -> None:
        result = self._run('{"role":"user","content":"   "}\n')
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertIn("no_content", result.stdout)


if __name__ == "__main__":
    unittest.main()
