#!/usr/bin/env python3
"""Block personal data from leaving the machine.

The repo is public, so the list of names worth blocking cannot live in it — that
list *is* the private data. It is derived at runtime instead:

- project slugs from the hub (`$MEMORY_HOME/chats/projects/*.md`) — exactly the
  set of real product names this machine works on
- the local account name and home directory
- structural shapes that need no list at all (`/Users/<someone>/`, encoded
  denylists)

On a machine with no hub — public CI, a fresh clone — the derived part is empty
and only the shape checks run. That is intentional: CI is the weaker net, the
pre-push hook is the real one.

Scans what is about to *leave*, not just the working tree: the leak this exists
to prevent shipped inside a tag whose content was never on the branch.

    check-local-leaks.py --staged            # pre-commit
    check-local-leaks.py --range A..B        # pre-push (per ref)
    check-local-leaks.py --rev v1.2.3        # one tag or commit, full tree
    check-local-leaks.py                     # working tree

Findings print redacted unless --show-matches: this runs in public CI logs.
"""

from __future__ import annotations

import argparse
import functools
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

#: Names that are meant to appear in examples and must never be flagged.
APPROVED_FICTIONAL = frozenset(
    {
        "example-app",
        "example-user",
        "other-app",
        "alpha-hub",
        "beta-app",
        "widget-ui",
        "acme",
        "example",
        "example.com",
        "example.org",
    }
)

#: Sub-tokens of a project slug that are ordinary vocabulary. `figma-frame-tools`
#: and `sdm-Codex` must not turn `tools` or `codex` into repo-wide tripwires —
#: they say nothing about the developer, and they appear in shipped prose.
GENERIC_SLUG_TOKENS = frozenset(
    {
        "agent",
        "app",
        "chat",
        "claude",
        "codex",
        "cursor",
        "data",
        "demo",
        "flutter",
        "hooks",
        "local",
        "main",
        "memory",
        "mobile",
        "plugin",
        "project",
        "python",
        "react",
        "scripts",
        "server",
        "shared",
        "skills",
        "test",
        "tests",
        "tools",
        "unified",
        "utils",
        "web",
    }
)

#: Placeholders a reader is meant to substitute — not anyone's real account.
PLACEHOLDER_USERS = "example-user|youruser|username|you|user|me|alice"

#: Shape checks — no list needed, so these work in CI too.
SUSPICIOUS_SHAPES: list[tuple[str, re.Pattern[str]]] = [
    ("home path with a real username", re.compile(rf"/Users/(?!(?:{PLACEHOLDER_USERS})\b)[A-Za-z][\w-]{{2,}}/")),
    ("home path with a real username", re.compile(rf"/home/(?!(?:{PLACEHOLDER_USERS})\b)[A-Za-z][\w-]{{2,}}/")),
    ("encoded/obfuscated denylist", re.compile(r"_DENY_CODES\s*[:=]|tuple\(\s*[\"']{2}\.join\(chr")),
    ("checkout-tied path", re.compile(r"~/Work/")),
]

#: Paths whose content is history, not shipped guidance.
SKIP_PARTS = {".git"}
# A checker states the patterns it forbids, so scanning one flags itself.
SKIP_NAMES = {
    "CHANGELOG.md",
    "check-local-leaks.py",
    "test_check_local_leaks.py",
    "test_no_hardcoded_paths.py",
}
# Everything textual is scanned. An allowlist of extensions used to skip .js,
# .html, .jsonl and extension-less scripts in silence: the same leak that fails
# in a .md passed unnoticed in any of those, and .jsonl is the transcript format
# a live token was once found in. Only known-binary payloads are skipped now.
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".bmp", ".tiff",
    ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".mp3", ".mp4", ".mov", ".avi", ".webm", ".wav", ".ogg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a", ".class", ".pyc",
}


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def repo_vocabulary(repo: Path) -> set[str]:
    """Words this project legitimately uses about itself.

    The hub also holds a project file for *this* repo, so without this the
    checker flags the product's own vocabulary — `memory`, `cursor`, `distill` —
    on nearly every line, and a check that fires everywhere gets switched off.
    """
    vocab: set[str] = {repo.name.lower()}
    for token in re.split(r"[-_\s]", repo.name):
        if token:
            vocab.add(token.lower())
    # Generic tech names the maintainer has cleared (one per line, no personal data).
    allow_file = repo / ".leakcheck-allow"
    if allow_file.is_file():
        for line in allow_file.read_text(encoding="utf-8").splitlines():
            word = line.split("#", 1)[0].strip().lower()
            if word:
                vocab.add(word)
    for manifest in (".cursor-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = repo / manifest
        if not path.is_file():
            continue
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for url_key in ("repository", "homepage"):
            url = str(data.get(url_key) or "").rstrip("/")
            if url:
                vocab.add(url.rsplit("/", 1)[-1].removesuffix(".git").lower())
        for value in [data.get("name", ""), *(data.get("keywords") or [])]:
            for token in re.split(r"[-_\s]", str(value)):
                if token:
                    vocab.add(token.lower())
            if value:
                vocab.add(str(value).lower())
    return vocab


def hub_terms(memory_home: Path | None = None, repo: Path | None = None) -> set[str]:
    """Real project names, read from the private hub — never from this repo."""
    if memory_home is None:
        try:
            from lib.memory_config import resolve_memory_home

            memory_home = resolve_memory_home(None, script_file=__file__)
        except Exception:
            return set()
    projects = Path(memory_home) / "chats" / "projects"
    if not projects.is_dir():
        return set()
    vocab = repo_vocabulary(repo) if repo is not None else set()
    out = set()
    for path in projects.glob("*.md"):
        slug = path.stem
        if slug.lower() in APPROVED_FICTIONAL or len(slug) < 4:
            continue
        candidates = {slug.lower()}
        # `motionlogger-flutter` must also flag a bare `motionlogger`.
        candidates.update(
            part.lower()
            for part in re.split(r"[-_]", slug)
            if len(part) >= 5 and part.lower() not in GENERIC_SLUG_TOKENS
        )
        out.update(c for c in candidates if c not in APPROVED_FICTIONAL and c not in vocab)
    return out


def identity_terms() -> set[str]:
    out = set()
    home = Path.home()
    user = home.name
    if user and user.lower() not in APPROVED_FICTIONAL and len(user) >= 3:
        out.add(user.lower())
    return out


@functools.lru_cache(maxsize=None)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Whole-word matcher.

    Sub-tokens of a slug are ordinary English often enough — `figma-frame-tools`
    yields `frame`, which as a bare substring hits every `framework` in the
    docs. Boundaries keep the real leak (`frame` standing alone) and drop the
    noise.
    """
    return re.compile(rf"(?<![0-9a-z]){re.escape(term)}(?![0-9a-z])")


def scan_text(text: str, terms: set[str]) -> list[tuple[int, str, str]]:
    """Return (line_no, reason, matched_text) for every hit."""
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for term in terms:
            if _term_pattern(term).search(lowered):
                hits.append((lineno, "local project or account name", term))
        for reason, pattern in SUSPICIOUS_SHAPES:
            found = pattern.search(line)
            if found:
                hits.append((lineno, reason, found.group(0)))
    return hits


def _should_scan(rel: str) -> bool:
    path = Path(rel)
    if SKIP_PARTS & set(path.parts) or path.name in SKIP_NAMES:
        return False
    return path.suffix.lower() not in SKIP_SUFFIXES


def _ignored_paths(repo: Path) -> set[str]:
    """Files git will never publish — including via the user's global ignore file."""
    out = _git(
        ["ls-files", "--others", "--ignored", "--exclude-standard"], repo
    ) or ""
    return {line for line in out.splitlines() if line}


def iter_worktree(repo: Path):
    ignored = _ignored_paths(repo)
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(repo))
        if rel in ignored:
            continue
        if _should_scan(rel):
            yield rel, path.read_text(encoding="utf-8", errors="replace")


def iter_git_files(repo: Path, rev: str):
    listing = _git(["ls-tree", "-r", "--name-only", rev], repo)
    for rel in listing.splitlines():
        if not _should_scan(rel):
            continue
        yield rel, _git(["show", f"{rev}:{rel}"], repo)


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def iter_range(repo: Path, rev_range: str):
    """Only the lines a push would add — an old file untouched by these commits
    is already public and re-flagging it would make the hook unusable.

    Yields one padded chunk per added line so the reported line number is the
    real one in the new file, not an offset into a diff.
    """
    diff = _git(["diff", "--unified=0", rev_range], repo)
    rel = ""
    lineno = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            rel = line[6:]
        elif line.startswith("@@"):
            match = _HUNK_RE.match(line)
            lineno = int(match.group(1)) if match else 0
        elif line.startswith("+") and not line.startswith("+++"):
            if rel and _should_scan(rel):
                yield rel, "\n" * (lineno - 1) + line[1:]
            lineno += 1


def iter_staged(repo: Path):
    names = _git(["diff", "--cached", "--name-only"], repo).splitlines()
    for rel in names:
        if _should_scan(rel):
            yield rel, _git(["show", f":{rel}"], repo)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="scan the index (pre-commit)")
    parser.add_argument("--range", dest="rev_range", help="scan lines added by A..B (pre-push)")
    parser.add_argument("--rev", help="scan the full tree of one commit or tag")
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--memory-home", help="hub path override")
    parser.add_argument(
        "--show-matches",
        action="store_true",
        help="print what matched — never use in public CI logs",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    terms = hub_terms(
        Path(args.memory_home) if args.memory_home else None, repo=repo
    ) | identity_terms()

    if args.staged:
        source, label = iter_staged(repo), "staged changes"
    elif args.rev_range:
        source, label = iter_range(repo, args.rev_range), f"lines added by {args.rev_range}"
    elif args.rev:
        source, label = iter_git_files(repo, args.rev), f"tree of {args.rev}"
    else:
        source, label = iter_worktree(repo), "working tree"

    findings: list[str] = []
    for rel, text in source:
        for lineno, reason, matched in scan_text(text, terms):
            shown = matched if args.show_matches else "[redacted]"
            findings.append(f"  {rel}:{lineno} — {reason}: {shown}")

    if findings:
        print(f"Local data would leak in {label}:", file=sys.stderr)
        print("\n".join(dict.fromkeys(findings)), file=sys.stderr)
        print(
            "\nThe repo is public. Replace with an approved fictional name "
            f"({', '.join(sorted(APPROVED_FICTIONAL)[:4])}, …) — see CONTRIBUTING.md.\n"
            "Re-run with --show-matches locally to see what matched.",
            file=sys.stderr,
        )
        return 1

    scope = f"{len(terms)} local term(s)" if terms else "shape checks only (no hub on this machine)"
    print(f"leak check clean: {label} · {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
