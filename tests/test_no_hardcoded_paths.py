"""Framework must not hardcode user-specific paths or personal project names.

Tests ship in the public repo. Examples and fixtures use an allowlisted set of
fictional identifiers only — never real client/product/machine names, even encoded.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import REPO_ROOT

# Documented shared hub is fine. Machine- or checkout-tied paths are not.
FORBIDDEN = [
    re.compile(r"~/Work/"),
    re.compile(r"~/agent-memory"),
    re.compile(r"\$HOME/agent-memory"),
    re.compile(r"~/.config/cursor-agent-memory"),
    re.compile(r"/Users/[^/\s]+/Work/"),
]
CURSOR_OK = re.compile(r"~/.cursor/")
SKIP_FILES = {
    "CHANGELOG.md",
    "test_no_hardcoded_paths.py",
    # States the shapes it forbids, so scanning it flags itself.
    "test_check_local_leaks.py",
    "check-local-leaks.py",
}
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

# Fictional identifiers allowed in examples / fixtures / docs.
# Add here when introducing a new generic name; do not add real products.
APPROVED_FICTIONAL = frozenset(
    {
        "example-app",
        "example-user",
        "other-app",
        "alpha-hub",
        "beta-app",
        "widget-ui",
        "acme",
        "example.org",
        "example.com",
    }
)

# Structural patterns that look like a maintainer's real workspace encoding.
# These are generic shape checks — not a personal denylist.
SUSPICIOUS_LOCAL_SHAPES = [
    # Encoded denylist / obfuscation of real names (bytes-as-ints tuples).
    re.compile(
        r"_DENY_CODES\s*[:=]|EXAMPLE_DENY\s*=\s*tuple\(\s*\"\"\.join\(chr",
        re.M,
    ),
    # Home-dir style paths with a non-example username segment.
    re.compile(r"/Users/(?!example-user|me|alice)[A-Za-z][A-Za-z0-9_-]{2,}/"),
    re.compile(r"/home/(?!example-user|me|alice)[A-Za-z][A-Za-z0-9_-]{2,}/"),
]

_EXAMPLE_SCAN_ROOTS = ("scripts", "tests", "templates", "docs", "hooks", "rules", "skills")
_EXAMPLE_SCAN_FILES = (
    "README.md",
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

    def test_no_obfuscated_or_personal_path_shapes(self) -> None:
        """Catch reintroduction of encoded personal denylists / real home paths."""
        self_path = Path(__file__).resolve()
        violations: list[str] = []
        for path in _iter_example_scan_files():
            if path.resolve() == self_path or path.name in SKIP_FILES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pat in SUSPICIOUS_LOCAL_SHAPES:
                if pat.search(text):
                    violations.append(f"{path.relative_to(REPO_ROOT)}: {pat.pattern[:60]}")
        self.assertEqual(
            violations,
            [],
            msg="Local / obfuscated naming shape in bundle:\n" + "\n".join(violations),
        )

    def test_approved_fictional_set_is_documented(self) -> None:
        """Keep the allowlist non-empty and aligned with CONTRIBUTING examples."""
        for name in ("example-app", "example-user", "other-app"):
            self.assertIn(name, APPROVED_FICTIONAL)


if __name__ == "__main__":
    unittest.main()
