#!/usr/bin/env python3
"""One-shot hub sync — scan, init, hooks, batch distill, GLOBAL_CONTEXT bootstrap."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.chats_manifest import load_manifest  # noqa: E402
from lib.global_context_bootstrap import bootstrap_global_context  # noqa: E402
from lib.memory_config import (  # noqa: E402
    persist_framework_root,
    resolve_framework_root,
    resolve_memory_home,
)
from lib.pending_chats import (  # noqa: E402
    list_chats_needing_distill,
    order_for_distill,
    scan_chat_stats,
)
from lib.boundary_hooks import distill_jsonl  # noqa: E402

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"
DEFAULT_DAYS = 180


def _run_init(framework_root: Path, memory_home: Path) -> dict:
    script = framework_root / "scripts" / "init-memory.sh"
    if not script.is_file():
        return {"status": "skipped", "reason": "no_init_script"}
    env = os.environ.copy()
    env["MEMORY_HOME"] = str(memory_home)
    proc = subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
    }


def _is_plugin_bundle(framework_root: Path) -> bool:
    return (framework_root / ".cursor-plugin" / "plugin.json").is_file()


def _install_hooks(framework_root: Path) -> dict:
    if _is_plugin_bundle(framework_root):
        return {"status": "skipped", "reason": "plugin_hooks_in_bundle"}
    script = framework_root / "scripts" / "install-memory-hooks.sh"
    if not script.is_file():
        return {"status": "skipped", "reason": "no_hooks_installer"}
    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
    }


def run_scan(
    *,
    memory_home: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict:
    """Fast chat inventory — ask user before distill."""
    return scan_chat_stats(memory_home, projects_root=projects_root)


def _resolve_pending(
    memory_home: Path,
    *,
    projects_root: Path,
    days: int,
    limit: int | None,
) -> tuple[list[dict], int, bool]:
    """Return (rows to process, total candidates before limit, truncated)."""
    all_pending = list_chats_needing_distill(
        memory_home,
        projects_root=projects_root,
        days=days,
        limit=None,
    )
    total = len(all_pending)
    if limit is not None and limit > 0:
        return order_for_distill(all_pending[:limit]), total, total > limit
    return order_for_distill(all_pending), total, False


def run_sync(
    *,
    memory_home: Path,
    framework_root: Path,
    days: int = DEFAULT_DAYS,
    dry_run: bool = False,
    install_hooks: bool = True,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
    limit: int | None = None,
    strategy: str = "auto",
) -> dict:
    report: dict = {
        "status": "ok",
        "memory_home": str(memory_home),
        "framework_root": str(framework_root),
        "days": days,
        "dry_run": dry_run,
        "limit": limit,
        "distills": 0,
        "distills_planned": 0,
        "distills_skipped": 0,
        "distills_errors": 0,
        "candidates": 0,
        "truncated": False,
        "projects": 0,
        "ready": False,
    }

    init_result = _run_init(framework_root, memory_home) if not dry_run else {"status": "dry_run"}
    report["init"] = init_result
    if not dry_run:
        persist_framework_root(
            framework_root.resolve(),
            memory_home=memory_home,
        )

    if install_hooks and not dry_run:
        report["hooks"] = _install_hooks(framework_root)
    else:
        report["hooks"] = {"status": "skipped" if dry_run else "disabled"}

    pending, candidates_total, truncated = _resolve_pending(
        memory_home, projects_root=projects_root, days=days, limit=limit
    )
    report["candidates"] = candidates_total
    report["truncated"] = truncated
    report["distills_planned"] = len(pending)

    distill_details: list[dict] = []
    if not dry_run:
        for row in pending:
            out = distill_jsonl(
                row["jsonl"],
                memory_home=memory_home,
                projects_root=projects_root,
                strategy=strategy,
                apply=True,
                bootstrap_decisions=True,
            )
            distill_details.append(
                {"chat_id": row["id"], "project": row["project"], **out}
            )
            st = out.get("status")
            if st == "distilled":
                report["distills"] += 1
            elif st == "error":
                report["distills_errors"] += 1
            else:
                report["distills_skipped"] += 1
    report["distill_details"] = distill_details

    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    if not dry_run:
        bootstrap = bootstrap_global_context(memory_home, manifest, dry_run=False)
        report["global_context"] = bootstrap
        report["projects"] = bootstrap.get("projects", 0)

        verify = subprocess.run(
            [
                sys.executable,
                str(framework_root / "scripts" / "verify-memory.py"),
                "--memory-home",
                str(memory_home),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        report["verify"] = {"returncode": verify.returncode}
        if verify.returncode != 0:
            report["status"] = "verify_failed"
    else:
        report["global_context"] = {"status": "dry_run"}
        report["verify"] = {"status": "dry_run"}

    report["ready"] = report["status"] == "ok" and not dry_run
    if dry_run:
        trunc_note = " (truncated by limit)" if truncated else ""
        report["message"] = (
            f"Preview: {report['distills_planned']} chat(s) would be distilled "
            f"from {candidates_total} pending in {days} days{trunc_note}. "
            f"Run without --dry-run after user confirms --days and --limit."
        )
    elif report["ready"]:
        trunc_note = f" ({candidates_total - report['distills']} skipped by limit)" if truncated else ""
        report["message"] = (
            f"Projects in GLOBAL_CONTEXT: {report['projects']}. "
            f"Chat distills: {report['distills']} ({days} days){trunc_note}. "
            f"Forward pointer: chats/projects/<slug>.md ## Next step. Ready to work."
        )
    else:
        report["message"] = "Sync incomplete — check report."
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home", help="Hub path override")
    parser.add_argument("--framework-root", help="Framework clone path")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--scan-only", action="store_true", help="Fast inventory only")
    parser.add_argument("--dry-run", action="store_true", help="Plan distill without writing")
    parser.add_argument("--no-hooks", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        help="Max chats to distill (user choice after --scan-only)",
    )
    parser.add_argument("--projects-root", metavar="DIR")
    parser.add_argument("-o", "--output", metavar="FILE")
    args = parser.parse_args()

    memory_home = resolve_memory_home(
        args.memory_home, script_file=str(SCRIPT_DIR / "sync-memory.py")
    )
    framework_root = resolve_framework_root(
        args.framework_root,
        script_file=str(SCRIPT_DIR / "sync-memory.py"),
        memory_home=memory_home,
    )
    if framework_root is None:
        framework_root = REPO_ROOT
    projects_root = (
        Path(args.projects_root).expanduser().resolve()
        if args.projects_root
        else DEFAULT_PROJECTS_ROOT
    )

    if args.scan_only:
        report = run_scan(memory_home=memory_home, projects_root=projects_root)
        exit_ok = True
    else:
        report = run_sync(
            memory_home=memory_home,
            framework_root=framework_root,
            days=args.days,
            dry_run=args.dry_run,
            install_hooks=not args.no_hooks,
            projects_root=projects_root,
            limit=args.limit,
            strategy="auto",
        )
        exit_ok = report["status"] == "ok" or args.dry_run

    out = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)

    return 0 if exit_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
