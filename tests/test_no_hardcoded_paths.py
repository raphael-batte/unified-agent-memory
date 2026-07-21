"""Framework must not hardcode user-specific paths or non-fictional example names."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import REPO_ROOT

# `~/.agent-memory` is the documented default hub shared by all environments, so it is
# allowed. What must never appear is a path tied to one machine or checkout.
FORBIDDEN = [
    re.compile(r"~/Work/"),
    re.compile(r"~/agent-memory"),
    re.compile(r"\$HOME/agent-memory"),
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

# Encoded maintainer denylist — decoded at runtime only (not plaintext in git).
_DENY_CODES: tuple[tuple[int, ...], ...] = (
    (116, 114, 101, 110, 100, 121, 109, 101, 110),
    (115, 116, 101, 97, 107, 108, 111, 118, 101, 114, 115),
    (115, 116, 101, 97, 107, 108, 111, 118, 101, 114),
    (115, 100, 109, 45, 117, 105, 50, 48, 50, 54),
    (115, 100, 109, 47, 117, 105, 50, 48, 50, 54),
    (119, 111, 114, 107, 47, 115, 100, 109),
    (116, 114, 101, 110, 100, 121, 109, 101, 110, 46, 114, 117),
    (114, 97, 112, 104, 98, 97, 116, 116, 101, 46, 99, 111, 109, 47, 116, 101, 115, 116),
)
EXAMPLE_DENY = tuple("".join(chr(c) for c in codes) for codes in _DENY_CODES)

_EXAMPLE_SCAN_ROOTS = ("scripts", "tests", "templates", "docs")
_EXAMPLE_SCAN_FILES = (
    "README.md",
    "CHANGELOG.md",
    "ARCHITECTURE.md",
    "INSTRUCTIONS.md",
    "ONBOARDING.md",
    "MIGRATION.md",
    "CONTRIBUTING.md",
)
_EXAMPLE_SUFFIXES = {".py", ".md", ".mdc", ".json", ".sh"}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _iter_example_scan_files() -> list[Path]:
    out: list[Path] = []
    for name in _EXAMPLE_SCAN_ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in _EXAMPLE_SUFFIXES:
                out.append(path)
    for name in _EXAMPLE_SCAN_FILES:
        path = REPO_ROOT / name
        if path.is_file():
            out.append(path)
    return sorted(set(out))


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

    def test_examples_use_fictional_names(self) -> None:
        violations: list[str] = []
        self_path = Path(__file__).resolve()
        for path in _iter_example_scan_files():
            if path.resolve() == self_path:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
            except OSError as exc:
                self.fail(f"cannot read {path}: {exc}")
            for needle in EXAMPLE_DENY:
                if needle in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)}: matched deny token")
        self.assertEqual(
            violations,
            [],
            msg="Non-fictional identifier in bundle:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
