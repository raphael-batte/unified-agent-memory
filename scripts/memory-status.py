#!/usr/bin/env python3
"""Dashboard: what's stored in the agent memory hub."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.defaults import ROTATION_WARN_LINES  # noqa: E402
from lib.memory_config import (  # noqa: E402
    framework_version,
    load_hub_config,
    resolve_framework_root,
    resolve_memory_home,
)

ROTATE_LINES = ROTATION_WARN_LINES
PROJECTS_ROOT = Path.home() / ".cursor/projects"
CURSOR_SKILLS = Path(
    os.environ.get("CURSOR_SKILLS", str(Path.home() / ".cursor/skills"))
).expanduser()

def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def line_count(path: Path) -> int:
    return len(read_text(path).splitlines()) if path.is_file() else 0


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def last_updated(path: Path) -> str | None:
    text = read_text(path)
    m = re.search(r"_Last updated[:\s_]*([0-9]{4}-[0-9]{2}-[0-9]{2})", text, re.I)
    return m.group(1) if m else None


def count_projects(global_context: Path) -> int:
    text = read_text(global_context)
    in_table = False
    count = 0
    for line in text.splitlines():
        if re.match(r"^##\s+Projects", line):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table and line.strip().startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
            if "Project" in line and "Path" in line:
                continue
            count += 1
    return count


def count_feedback_bullets(path: Path, prefix: str) -> int:
    text = read_text(path)
    return len(re.findall(rf"^{re.escape(prefix)}\s", text, re.M))


def count_superseded(fails: Path) -> int:
    return len(re.findall(r"_superseded\b", read_text(fails), re.I))


def count_open_fail_bullets(fails: Path) -> int:
    """Fail bullets without a following _superseded_ marker."""
    lines = read_text(fails).splitlines()
    open_n = 0
    for i, line in enumerate(lines):
        if not re.match(r"^-\s", line):
            continue
        superseded = False
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if not nxt:
                continue
            if "_superseded" in nxt.lower():
                superseded = True
            break
        if not superseded:
            open_n += 1
    return open_n


def count_topics(path: Path) -> int:
    return len(re.findall(r"^##\s+", read_text(path), re.M))


def in_archive(path: Path, memory_home: Path) -> bool:
    try:
        return "archive" in path.relative_to(memory_home).parts
    except ValueError:
        return False


def layer_stats(memory_home: Path) -> dict[str, dict]:
    layers = {
        "context": memory_home / "context",
        "feedback": memory_home / "feedback",
        "chats": memory_home / "chats",
    }
    out: dict[str, dict] = {}
    for name, root in layers.items():
        if not root.is_dir():
            out[name] = {"files": 0, "bytes": 0, "lines": 0}
            continue
        files = [p for p in root.rglob("*") if p.is_file() and not in_archive(p, memory_home)]
        lines = sum(line_count(p) for p in files if p.suffix == ".md")
        out[name] = {
            "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
            "lines": lines,
        }
    return out


def rotation_warnings(memory_home: Path, threshold: int) -> list[str]:
    warn: list[str] = []
    for sub in ("context", "feedback"):
        root = memory_home / sub
        if root.is_dir():
            for p in sorted(root.rglob("*.md")):
                if in_archive(p, memory_home):
                    continue
                n = line_count(p)
                if n >= threshold:
                    rel = p.relative_to(memory_home)
                    warn.append(f"{rel} ({n} lines)")
    projects = memory_home / "chats" / "projects"
    if projects.is_dir():
        for p in sorted(projects.glob("*.md")):
            if p.name == "example.md":
                continue
            n = line_count(p)
            if n >= threshold:
                warn.append(f"chats/projects/{p.name} ({n} lines)")
    return warn


def pending_chats_count(memory_home: Path) -> tuple[int, int]:
    lc = load_script_module("list_chats", "list-chats.py")
    processed, pending, _total = lc.chat_counts(memory_home, PROJECTS_ROOT)
    return processed, pending


def load_script_module(module_name: str, filename: str):
    import importlib.util

    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def project_distills(memory_home: Path) -> list[tuple[str, int]]:
    projects = memory_home / "chats" / "projects"
    if not projects.is_dir():
        return []
    rows = []
    for p in sorted(projects.glob("*.md")):
        if p.name == "example.md":
            continue
        rows.append((p.stem, line_count(p)))
    return rows


def skills_stats(memory_home: Path, framework_root: Path | None) -> dict:
    cursor: list[dict] = []
    if CURSOR_SKILLS.is_dir():
        for entry in sorted(CURSOR_SKILLS.iterdir()):
            if entry.name.startswith("."):
                continue
            item: dict = {"name": entry.name, "kind": "personal", "target": None, "ok": True}
            if entry.is_symlink():
                item["target"] = str(entry.resolve())
                item["ok"] = entry.exists()
                if framework_root:
                    try:
                        Path(item["target"]).resolve().relative_to(
                            framework_root.resolve()
                        )
                        item["kind"] = "framework"
                    except ValueError:
                        pass
            elif entry.is_dir() and (entry / "SKILL.md").is_file():
                item["target"] = str(entry)
            cursor.append(item)

    hub_skills = memory_home / "skills"
    personal_hub: list[str] = []
    if hub_skills.is_dir():
        for d in sorted(hub_skills.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                personal_hub.append(d.name)

    linked_names = {c["name"] for c in cursor if c.get("ok")}
    unlinked = [n for n in personal_hub if n not in linked_names]

    return {
        "cursor": cursor,
        "hub_personal": personal_hub,
        "unlinked": unlinked,
        "framework_linked": sum(1 for c in cursor if c["kind"] == "framework" and c["ok"]),
        "personal_linked": sum(1 for c in cursor if c["kind"] == "personal" and c["ok"]),
    }


def verify_summary(memory_home: Path) -> tuple[int, int] | None:
    vm = load_script_module("verify_memory", "verify-memory.py")
    results, _warnings = vm.run_checks_for_hub(memory_home)
    return vm.summarize_results(results)


def metrics_health(memory_home: Path) -> dict | None:
    try:
        from lib.distill_metrics import read_metrics

        mh = load_script_module("memory_health", "memory-health.py")
        rows = read_metrics(memory_home)
        data = mh.analyze_metrics(rows, days=7)
        return mh.enrich_with_baseline(memory_home, data, update_baseline=False)
    except Exception:
        return None


def collect(memory_home: Path, framework_root: Path | None) -> dict:
    wins = memory_home / "feedback" / "wins.md"
    fails = memory_home / "feedback" / "fails.md"
    gc = memory_home / "context" / "GLOBAL_CONTEXT.md"
    conv = memory_home / "context" / "conventions.md"
    infra = memory_home / "context" / "infra.md"
    pref = memory_home / "context" / "preferences.md"

    win_n = count_feedback_bullets(wins, "+")
    fail_n = count_feedback_bullets(fails, "-")
    superseded = count_superseded(fails)
    fail_open = count_open_fail_bullets(fails)
    processed, pending = pending_chats_count(memory_home)
    layers = layer_stats(memory_home)
    active_bytes = sum(layers[k]["bytes"] for k in ("context", "feedback", "chats"))
    sources_bytes = dir_size(memory_home / "sources")

    return {
        "memory_home": str(memory_home),
        "framework_root": str(framework_root) if framework_root else None,
        "framework_version": framework_version(framework_root),
        "projects": count_projects(gc),
        "conventions_lines": line_count(conv),
        "infra_lines": line_count(infra),
        "preferences_lines": line_count(pref),
        "conventions_updated": last_updated(conv),
        "wins": win_n,
        "fails": fail_n,
        "fails_open": fail_open,
        "fails_superseded": superseded,
        "win_topics": count_topics(wins),
        "fail_topics": count_topics(fails),
        "chats_processed": processed,
        "chats_pending": pending,
        "project_distills": project_distills(memory_home),
        "layers": layers,
        "active_bytes": active_bytes,
        "sources_bytes": sources_bytes,
        "skills_hub": len(list((memory_home / "skills").iterdir())) if (memory_home / "skills").is_dir() else 0,
        "skills": skills_stats(memory_home, framework_root),
        "rotation": rotation_warnings(memory_home, ROTATE_LINES),
        "verify": verify_summary(memory_home),
        "metrics_health": metrics_health(memory_home),
        "config": load_hub_config(memory_home),
    }


def print_dashboard(data: dict) -> None:
    print("Agent Memory Status")
    print(f"  Hub: {data['memory_home']}")
    if data["framework_root"]:
        ver = data.get("framework_version") or "?"
        print(f"  Framework: {data['framework_root']} v{ver}")
    print()

    print("── Context ──────────────────────────────")
    print(f"  Projects:       {data['projects']}")
    upd = data.get("conventions_updated") or "—"
    print(f"  Conventions:    {data['conventions_lines']} lines  · last {upd}")
    print(f"  Infra:          {data['infra_lines']} lines")
    print(f"  Preferences:    {data['preferences_lines']} lines")
    print()

    print("── Feedback ─────────────────────────────")
    print(f"  Wins (+):       {data['wins']}  ({data['win_topics']} topics)")
    print(
        f"  Fails (−):      {data['fails']} total · "
        f"{data['fails_open']} open · {data['fails_superseded']} superseded"
    )
    print()

    print("── Chats ────────────────────────────────")
    print(f"  Distilled:      {data['chats_processed']} processed · {data['chats_pending']} pending")
    distills = data["project_distills"]
    names = ", ".join(d[0] for d in distills) if distills else "—"
    total_lines = sum(d[1] for d in distills)
    print(f"  Project files:  {len(distills)} ({names})")
    print(f"  Lines (active): {total_lines} across projects/")
    print()

    print("── Volume (active layers) ───────────────")
    for layer in ("context", "feedback", "chats"):
        s = data["layers"][layer]
        print(f"  {layer + '/':<14} {s['files']} files   {fmt_size(s['bytes'])}")
    print(f"  Total active:   {fmt_size(data['active_bytes'])}")
    print(f"  sources/        {fmt_size(data['sources_bytes'])} (reference only)")
    print()

    rot = data["rotation"]
    print(f"── Rotation watch (≥{ROTATE_LINES} lines) ───────────")
    if rot:
        for w in rot:
            print(f"  ⚠ {w}")
    else:
        print("  ✓ all active layer files below threshold")
    print()

    sk = data["skills"]
    print("── Cursor skills ──────────────────────────")
    print(
        f"  ~/.cursor/skills:  {len(sk['cursor'])} entries "
        f"({sk['framework_linked']} framework · {sk['personal_linked']} personal)"
    )
    hub_n = len(sk["hub_personal"])
    unlinked = len(sk["unlinked"])
    print(f"  $MEMORY_HOME/skills: {hub_n} domain skill(s) · {unlinked} not linked to Cursor")
    print()

    if data.get("verify"):
        passed, failed = data["verify"]
        mark = "✓" if failed == 0 else "✗"
        print("── Health (verify-memory) ─────────────────")
        print(f"  {mark} {passed}/{passed + failed} checks passed")
        print()

    mh = data.get("metrics_health")
    if mh:
        print("── Distill metrics (7d) ───────────────────")
        rate = mh.get("pointer_extracted_rate")
        rate_s = f"{rate * 100:.0f}%" if rate is not None else "—"
        print(
            f"  {mh.get('distilled', 0)} distilled · "
            f"{mh.get('skipped', 0)} skipped · "
            f"{mh.get('errors', 0)} errors"
        )
        print(f"  Pointer extracted: {rate_s} · avg {mh.get('avg_distill_ms') or '—'} ms")
        deg = mh.get("degradation") or {}
        if deg.get("degraded"):
            print(f"  ⚠ {deg.get('degradation_reason')}")
        bl = mh.get("baseline") or {}
        if bl.get("median_hit_rate") is not None:
            print(f"  Baseline median: {float(bl['median_hit_rate']) * 100:.0f}%")
        print()


def print_brief(data: dict) -> None:
    distills = len(data["project_distills"])
    print(
        f"{data['projects']} projects · "
        f"{data['chats_processed']} chats · "
        f"+{data['wins']}/−{data['fails']} feedback · "
        f"{fmt_size(data['active_bytes'])} active · "
        f"{data['chats_pending']} pending · "
        f"{distills} distills"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home", help="Override hub path (default: config/env)")
    parser.add_argument("--framework-root", help="Override framework clone path")
    parser.add_argument("--brief", action="store_true", help="One-line summary")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--no-verify", action="store_true", help="Skip verify-memory summary")
    args = parser.parse_args()

    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    framework_root = resolve_framework_root(
        args.framework_root,
        script_file=__file__,
        memory_home=memory_home,
    )
    if not memory_home.is_dir():
        print(f"Memory hub not found: {memory_home}", file=sys.stderr)
        print("Run: bash scripts/init-memory.sh", file=sys.stderr)
        return 1

    data = collect(memory_home, framework_root)
    if args.no_verify:
        data["verify"] = None

    if args.json:
        print(json.dumps(data, indent=2))
    elif args.brief:
        print_brief(data)
    else:
        print_dashboard(data)

    return 0


if __name__ == "__main__":
    sys.exit(main())
