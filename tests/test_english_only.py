"""Framework repo must not contain Cyrillic — English only in docs, scripts, skills."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import REPO_ROOT

CYRILLIC = re.compile(r"[\u0400-\u04FF]")

SCAN_SUFFIXES = {
    ".md",
    ".mdc",
    ".py",
    ".sh",
    ".json",
    ".jsonl",
    ".txt",
    ".phtm",
}

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "memory"}
def iter_repo_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        parts = path.parts
        if "templates" in parts and "lang" in parts:
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        yield path


class TestEnglishOnly(unittest.TestCase):
    def test_no_cyrillic_in_framework_repo(self) -> None:
        offenders: list[str] = []
        for path in iter_repo_text_files(REPO_ROOT):
            text = path.read_text(encoding="utf-8", errors="replace")
            if CYRILLIC.search(text):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(str(rel))
        self.assertEqual(
            offenders,
            [],
            "Cyrillic found in framework files (English only):\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
