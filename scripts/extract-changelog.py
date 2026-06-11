#!/usr/bin/env python3
"""Extract one version section from CHANGELOG.md for GitHub Release notes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SECTION_START = re.compile(r"^##\s+\[([^\]]+)\]", re.M)
VERSION_LINE = re.compile(r"^##\s+\[")


def extract_section(changelog: str, version: str) -> str:
    """Return body of ## [version] up to (not including) the next ## [."""
    ver = version.strip().lstrip("v")
    starts = list(SECTION_START.finditer(changelog))
    if not starts:
        raise ValueError("no version sections found in CHANGELOG")

    for i, match in enumerate(starts):
        if match.group(1).strip() != ver:
            continue
        body_start = match.end()
        if i + 1 < len(starts):
            body_end = starts[i + 1].start()
        else:
            body_end = len(changelog)
        body = changelog[body_start:body_end].strip()
        if not body:
            raise ValueError(f"empty section for version {ver}")
        return f"## [{ver}]\n\n{body}"

    raise ValueError(f"version {ver} not found in CHANGELOG")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="SemVer without v prefix")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "CHANGELOG.md",
    )
    args = parser.parse_args()

    version = args.version
    if not version:
        version_path = args.changelog.parent / "VERSION"
        if not version_path.is_file():
            print("VERSION file missing and no version argument", file=sys.stderr)
            sys.exit(1)
        version = version_path.read_text(encoding="utf-8").strip()

    text = args.changelog.read_text(encoding="utf-8")
    try:
        section = extract_section(text, version)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(section)


if __name__ == "__main__":
    main()
