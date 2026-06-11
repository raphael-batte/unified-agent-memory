"""Tests for scripts/extract-changelog.py"""

from __future__ import annotations

import unittest

from helpers import load_script_module

ec = load_script_module("extract_changelog", "extract-changelog.py")
extract_section = ec.extract_section

SAMPLE = """# Changelog

## [Unreleased]

## [0.5.0] - 2026-06-06

### Added

- Release workflow

### Fixed

- Summary bookkeeping

## [0.4.3] - 2026-06-06

### Fixed

- English only

## [0.4.0] - 2026-06-06

### Added

- semantic-merge
"""


class TestExtractChangelog(unittest.TestCase):
    def test_extracts_target_section_only(self) -> None:
        section = extract_section(SAMPLE, "0.5.0")
        self.assertIn("Release workflow", section)
        self.assertIn("Summary bookkeeping", section)
        self.assertNotIn("English only", section)
        self.assertNotIn("semantic-merge", section)
        self.assertTrue(section.startswith("## [0.5.0]"))

    def test_missing_version_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_section(SAMPLE, "9.9.9")

    def test_no_leak_into_adjacent_versions(self) -> None:
        section = extract_section(SAMPLE, "0.4.3")
        self.assertIn("English only", section)
        self.assertNotIn("Release workflow", section)
        self.assertNotIn("semantic-merge", section)


if __name__ == "__main__":
    unittest.main()
