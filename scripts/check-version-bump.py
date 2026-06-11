#!/usr/bin/env python3
"""CI check: behaviour-changing diffs must update VERSION or CHANGELOG."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOC_ONLY_PREFIXES = ("README", "docs/", "templates/")
META_ONLY = {"LICENSE", ".gitignore", ".cursor/rules/versioning.mdc"}


def changed_files(base_ref: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT,
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_doc_only(path: str) -> bool:
    if path in META_ONLY:
        return True
    if path.startswith(DOC_ONLY_PREFIXES) or path == "README.md":
        return True
    return False


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    try:
        files = changed_files(base)
    except subprocess.CalledProcessError:
        # First commit or missing base — skip
        return 0
    if not files:
        return 0

    behaviour = False
    version_touched = False
    for path in files:
        if path in ("VERSION", "CHANGELOG.md"):
            version_touched = True
        if not is_doc_only(path):
            behaviour = True

    if not behaviour:
        return 0
    if version_touched:
        return 0

    print(
        "Behaviour-changing files without VERSION/CHANGELOG update.\n"
        "Run: bash scripts/bump-version.sh patch \"description\"",
        file=sys.stderr,
    )
    for path in files:
        if not is_doc_only(path) and path not in ("VERSION", "CHANGELOG.md"):
            print(f"  - {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
