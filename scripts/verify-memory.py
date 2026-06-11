#!/usr/bin/env python3
"""Verify agent memory hub integrity. Run weekly or after structural changes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.defaults import MAX_LAYER_FILE_LINES  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.gitleaks_scan import (  # noqa: E402
    findings_to_hits,
    gitleaks_available,
    scan_path_with_gitleaks,
)
from lib.cross_layer_warnings import collect_cross_layer_warnings  # noqa: E402
from lib.chats_manifest import manifest_desync_warning  # noqa: E402
from lib.secrets_guard import scan_memory_hub  # noqa: E402
from lib.timestamps import parse_distilled_at  # noqa: E402

LEGACY_LINE_REF = re.compile(r"conventions\.md:\d+", re.I)
SUPERSEDED_SECTION = re.compile(
    r"_superseded\s*→\s*conventions\.md\s*§\s*(.+?)(?:\s*\([^)]*\))?\s*_",
    re.I,
)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def extract_convention_headings(text: str) -> set[str]:
    return {m.group(1).strip() for m in HEADING_RE.finditer(text)}


def in_archive(path: Path, memory_home: Path) -> bool:
    try:
        rel = path.relative_to(memory_home)
    except ValueError:
        return False
    return "archive" in rel.parts


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail


def check_global_context(memory_home: Path) -> CheckResult:
    path = memory_home / "context" / "GLOBAL_CONTEXT.md"
    lines = line_count(path)
    if not path.is_file():
        return CheckResult("GLOBAL_CONTEXT.md exists", False, "file missing")
    if lines <= 10:
        return CheckResult("GLOBAL_CONTEXT.md exists", False, f"only {lines} lines (need > 10)")
    return CheckResult("GLOBAL_CONTEXT.md exists", True, f"{lines} lines")


def check_conventions(memory_home: Path) -> CheckResult:
    path = memory_home / "context" / "conventions.md"
    text = read_text(path)
    if not path.is_file():
        return CheckResult("conventions.md", False, "file missing")
    lines = line_count(path)
    if lines < 5:
        return CheckResult("conventions.md", False, f"only {lines} lines (need ≥ 5)")
    if "## " not in text:
        return CheckResult("conventions.md", False, "no ## sections")
    return CheckResult("conventions.md", True, f"{lines} lines, has sections")


def check_feedback_fails(memory_home: Path) -> CheckResult:
    path = memory_home / "feedback" / "fails.md"
    text = read_text(path)
    if not path.is_file():
        return CheckResult("feedback/fails.md structure", False, "file missing")
    blocks = re.findall(r"^##\s+", text, re.M)
    if not blocks:
        return CheckResult("feedback/fails.md structure", False, "no ## topic blocks")
    return CheckResult("feedback/fails.md structure", True, f"{len(blocks)} topic block(s)")


def check_manifest(memory_home: Path) -> CheckResult:
    path = memory_home / "chats" / "manifest.json"
    if not path.is_file():
        return CheckResult("manifest.json distilled_at", False, "file missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("manifest.json distilled_at", False, f"invalid JSON: {exc}")

    processed = data.get("processed", [])
    if not isinstance(processed, list):
        return CheckResult("manifest.json distilled_at", False, "processed is not a list")

    bad: list[str] = []
    for entry in processed:
        if not isinstance(entry, dict):
            bad.append("(non-object entry)")
            continue
        uid = entry.get("id", "?")
        raw_at = entry.get("distilled_at")
        if not raw_at:
            bad.append(str(uid)[:8])
            continue
        if parse_distilled_at(str(raw_at)) is None:
            bad.append(f"{str(uid)[:8]}(bad format)")

    if bad:
        return CheckResult(
            "manifest.json distilled_at",
            False,
            f"missing or invalid distilled_at for: {', '.join(bad[:5])}"
            + (" …" if len(bad) > 5 else ""),
        )
    return CheckResult(
        "manifest.json distilled_at",
        True,
        f"{len(processed)} processed entry(ies) OK",
    )


def check_superseded_refs(memory_home: Path) -> CheckResult:
    fails_path = memory_home / "feedback" / "fails.md"
    conv_path = memory_home / "context" / "conventions.md"
    fails_text = read_text(fails_path)
    conv_text = read_text(conv_path)

    if not fails_path.is_file():
        return CheckResult("superseded § refs", False, "feedback/fails.md missing")
    if not conv_path.is_file():
        return CheckResult("superseded § refs", False, "conventions.md missing")

    if LEGACY_LINE_REF.search(fails_text):
        return CheckResult(
            "superseded § refs",
            False,
            "legacy conventions.md:NN line refs found — use § <heading>",
        )

    headings = extract_convention_headings(conv_text)
    refs = [m.group(1).strip() for m in SUPERSEDED_SECTION.finditer(fails_text)]
    if not refs:
        return CheckResult("superseded § refs", True, "no conventions § refs (OK if empty)")

    unknown = [r for r in refs if r not in headings]
    if unknown:
        return CheckResult(
            "superseded § refs",
            False,
            f"unknown headings: {', '.join(unknown)}",
        )
    return CheckResult("superseded § refs", True, f"{len(refs)} ref(s) valid")


def layer_md_paths(memory_home: Path) -> list[Path]:
    paths: list[Path] = []
    for sub in ("context", "feedback"):
        root = memory_home / sub
        if root.is_dir():
            paths.extend(root.rglob("*.md"))
    projects = memory_home / "chats" / "projects"
    if projects.is_dir():
        paths.extend(projects.glob("*.md"))
    for name in ("INDEX.md", "README.md"):
        p = memory_home / name
        if p.is_file():
            paths.append(p)
    return paths


def check_oversized_files(memory_home: Path, max_lines: int) -> CheckResult:
    offenders: list[str] = []
    for path in sorted(set(layer_md_paths(memory_home))):
        if in_archive(path, memory_home):
            continue
        lines = line_count(path)
        if lines > max_lines:
            try:
                rel = path.relative_to(memory_home)
            except ValueError:
                rel = path
            offenders.append(f"{rel} ({lines} lines)")

    if offenders:
        shown = ", ".join(offenders[:4])
        suffix = " …" if len(offenders) > 4 else ""
        return CheckResult(
            "no oversized layer .md",
            False,
            f">{max_lines} lines: {shown}{suffix}",
        )
    return CheckResult(
        "no oversized layer .md",
        True,
        f"context/feedback/chats/projects ≤ {max_lines} lines",
    )


def check_gitleaks(memory_home: Path, *, required: bool = False) -> CheckResult:
    if not gitleaks_available():
        if required:
            return CheckResult(
                "gitleaks scan",
                False,
                "gitleaks not installed (brew install gitleaks)",
            )
        return CheckResult(
            "gitleaks scan",
            True,
            "skipped (gitleaks not installed)",
        )

    findings, err = scan_path_with_gitleaks(memory_home)
    hits = findings_to_hits(findings, memory_home)
    if err and not hits:
        return CheckResult("gitleaks scan", False, err)
    if hits:
        path, line_no, label, preview = hits[0]
        try:
            rel = path.relative_to(memory_home)
        except ValueError:
            rel = path
        detail = f"{rel}:{line_no} ({label}) {preview!r}"
        if len(hits) > 1:
            detail += f" (+{len(hits) - 1} more)"
        return CheckResult("gitleaks scan", False, detail)
    return CheckResult("gitleaks scan", True, "no gitleaks findings")


def check_no_secrets(memory_home: Path, *, strict: bool = False) -> CheckResult:
    hits = scan_memory_hub(memory_home, strict=strict)
    label = "no secrets in hub" + (" (strict)" if strict else "")
    if not hits:
        detail = "context/feedback/chats clean"
        if strict:
            detail += " — regex + entropy"
        return CheckResult(label, True, detail)
    path, line_no, hit_label, preview = hits[0]
    try:
        rel = path.relative_to(memory_home)
    except ValueError:
        rel = path
    detail = f"{rel}:{line_no} ({hit_label}) {preview!r}"
    if len(hits) > 1:
        detail += f" (+{len(hits) - 1} more)"
    return CheckResult(label, False, detail)


def run_checks_for_hub(
    memory_home: Path,
    *,
    max_file_lines: int = MAX_LAYER_FILE_LINES,
    strict_secrets: bool = False,
    gitleaks: bool = False,
    gitleaks_required: bool = False,
) -> tuple[list[CheckResult], list[str]]:
    """Run all checks. Returns (results, warnings). Warnings do not fail verify."""
    args_ns = argparse.Namespace(
        memory_home=str(memory_home),
        max_file_lines=max_file_lines,
        strict_secrets=strict_secrets,
        quiet=False,
    )
    results = [
        check_global_context(memory_home),
        check_conventions(memory_home),
        check_feedback_fails(memory_home),
        check_manifest(memory_home),
        check_superseded_refs(memory_home),
        check_no_secrets(memory_home, strict=strict_secrets),
        check_oversized_files(memory_home, max_file_lines),
    ]
    if gitleaks or gitleaks_required:
        results.append(check_gitleaks(memory_home, required=gitleaks_required))
    warnings = collect_cross_layer_warnings(memory_home)
    desync = manifest_desync_warning(memory_home)
    if desync:
        warnings.append(desync)
    _ = args_ns  # reserved for future threshold overrides from hub config
    return results, warnings


def run_checks(args: argparse.Namespace) -> tuple[list[CheckResult], list[str]]:
    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    return run_checks_for_hub(
        memory_home,
        max_file_lines=args.max_file_lines,
        strict_secrets=args.strict_secrets,
        gitleaks=args.gitleaks,
        gitleaks_required=args.gitleaks_required,
    )


def summarize_results(results: list[CheckResult]) -> tuple[int, int]:
    passed = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)
    return passed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home")
    parser.add_argument("--max-file-lines", type=int, default=MAX_LAYER_FILE_LINES)
    parser.add_argument(
        "--strict-secrets",
        action="store_true",
        help="Also flag high-entropy tokens (best-effort, may false-positive)",
    )
    parser.add_argument(
        "--gitleaks",
        action="store_true",
        help="Run gitleaks on hub if installed (skip if missing)",
    )
    parser.add_argument(
        "--gitleaks-required",
        action="store_true",
        help="Require gitleaks scan (fail if binary missing)",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    print(f"Memory hub: {memory_home}")
    print()

    results, warnings = run_checks(args)
    passed, failed = summarize_results(results)

    for result in results:
        if result.ok:
            if not args.quiet:
                print(f"✅ {result.name} — {result.detail}")
        else:
            print(f"❌ {result.name} — {result.detail}")

    for warn in warnings:
        print(f"⚠️  {warn}")

    print()
    print(f"{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
