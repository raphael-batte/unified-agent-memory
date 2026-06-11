"""Framework must not hardcode user-specific install or hub directories."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import REPO_ROOT

FORBIDDEN = [
    re.compile(r"~/Work/"),
    re.compile(r"~/agent-memory"),
    re.compile(r"\$HOME/agent-memory"),
    re.compile(r"~/.agent-memory"),
    re.compile(r"~/.config/cursor-agent-memory"),
    re.compile(r"/Users/[^/\s]+/Work/"),
]
# Cursor integration paths are allowed in these locations only
CURSOR_OK = re.compile(r"~/.cursor/")
SKIP_FILES = {"CHANGELOG.md", "test_no_hardcoded_paths.py"}
SKIP_SUFFIXES = {".jsonl"}
ALLOW_IF_ONLY_CURSOR = {
    "scripts/lib/config.sh",
    "scripts/lib/memory_config.py",
    "scripts/lib/hook_env.sh",
    "scripts/link-cursor-skills.sh",
    "scripts/install-memory-hooks.sh",
    "scripts/lib/hooks_config.py",
    "scripts/memory-status.py",
    "scripts/lib/pending_chats.py",
    "scripts/distill-extract.py",
}
CURSOR_HOOK_GLOB = "templates/cursor-hooks/"


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


class TestNoHardcodedPaths(unittest.TestCase):
    def test_no_fixed_user_paths_in_repo(self) -> None:
        offenders: list[str] = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            rel = _rel(path)
            if path.name in SKIP_FILES or path.suffix in SKIP_SUFFIXES:
                continue
            if path.suffix not in {".md", ".mdc", ".sh", ".py", ".json"}:
                continue
            if rel.startswith(".cursor/") or rel.startswith("memory/"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pat in FORBIDDEN:
                if not pat.search(text):
                    continue
                if rel in ALLOW_IF_ONLY_CURSOR:
                    if not pat.search(CURSOR_OK.sub("", text)):
                        break
                if CURSOR_HOOK_GLOB in rel.replace("\\", "/"):
                    break
                offenders.append(f"{rel} ({pat.pattern})")
                break
        self.assertEqual(offenders, [], "Hardcoded user paths:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
