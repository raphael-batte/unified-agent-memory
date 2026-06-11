"""User-facing docs must not mention removed second-machine / dev-clone / handoff flows."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import REPO_ROOT

# CHANGELOG is historical; hub memory/ is user data.
SCAN_ROOTS = (
    "README.md",
    "ONBOARDING.md",
    "MIGRATION.md",
    "ARCHITECTURE.md",
    "INSTRUCTIONS.md",
    "CONTRIBUTING.md",
    "docs",
    "skills",
    "SKILL.md",
    "templates",
)

FORBIDDEN = [
    re.compile(r"second[\s-]machine", re.I),
    re.compile(r"two[\s-]clone", re.I),
    re.compile(r"dev\.config\.json", re.I),
    re.compile(r"sync-to-install", re.I),
    re.compile(r"AGENT_HANDOFF", re.I),
    re.compile(r"handoff_mode", re.I),
    re.compile(r"agent-handoff", re.I),
    re.compile(r"repo-handoff", re.I),
    re.compile(r"\bhandoff\b", re.I),
    re.compile(r"<install>/memory", re.I),
    re.compile(r"install-memory-hooks", re.I),
]


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for rel in SCAN_ROOTS:
        path = REPO_ROOT / rel
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out.extend(p for p in path.rglob("*") if p.is_file() and p.suffix in {".md", ".mdc", ".sh", ".json", ".in"})
    return out


class TestNoLegacyNarrative(unittest.TestCase):
    def test_user_facing_docs_have_no_legacy_flows(self) -> None:
        offenders: list[str] = []
        for path in _iter_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(REPO_ROOT)
            for pat in FORBIDDEN:
                if pat.search(text):
                    offenders.append(f"{rel} ({pat.pattern})")
                    break
        self.assertEqual(
            offenders,
            [],
            "Legacy narrative in user-facing files:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
