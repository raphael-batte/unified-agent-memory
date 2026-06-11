"""First-run bootstrap — hub init, scan, scope, batch distill (sessionStart)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from lib.chats_manifest import load_manifest, processed_by_id
from lib.global_context_bootstrap import bootstrap_global_context
from lib.memory_config import persist_paths, resolve_plugin_root
from lib.pending_chats import list_chats_needing_distill, scan_chat_stats
from lib.project_merge import apply_mechanical_auto_decisions

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"
STATE_DIR = ".state"
INITIALIZED_FILE = "initialized"
SCOPE_FILE = "first-run-scope.json"
STATE_FILE = "first-run.json"

AUTO_PENDING_90D_MAX = 40
AUTO_SCOPE = {"days": 90, "limit": 40}
ASK_PENDING_90D_MIN = 41

SCOPE_PRESETS: dict[str, dict[str, int | None]] = {
    "7d": {"days": 7, "limit": None},
    "90d-30": {"days": 90, "limit": 30},
    "180d-all": {"days": 180, "limit": None},
    "new-only": {"days": 180, "limit": 15},
}

SETUP_HOOK_MESSAGE = """[agent-memory] Hub ready at {hub}

Complete setup in chat: @agent-memory → **set up agent memory**

(Custom hub path or migrate from an old hub — answer in that chat; agent runs init/migrate/doctor.)"""

SCOPE_PROMPT = """[agent-memory] Choose distill scope ({pending_90d} pending in 90d, {total} total chats).

Presets:
  7d        — last 7 days
  90d-30    — 90 days, max 30 chats
  180d-all  — 180 days, all pending
  new-only  — 180 days, max 15 newest pending

Run: python3 scripts/first-run-scope.py --preset <name>
Then: python3 scripts/first-run-continue.py

Scan: {scan_json}"""


def _state_dir(memory_home: Path) -> Path:
    return memory_home / STATE_DIR


def is_initialized(memory_home: Path) -> bool:
    return (_state_dir(memory_home) / INITIALIZED_FILE).is_file()


def mark_initialized(memory_home: Path, stats: dict[str, Any] | None = None) -> None:
    d = _state_dir(memory_home)
    d.mkdir(parents=True, exist_ok=True)
    (d / INITIALIZED_FILE).touch()
    if stats is not None:
        (d / STATE_FILE).write_text(
            json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def read_scope(memory_home: Path) -> dict[str, Any] | None:
    raw = _load_json(_state_dir(memory_home) / SCOPE_FILE)
    if not raw:
        return None
    days = int(raw.get("days", 180))
    limit = raw.get("limit")
    return {"days": days, "limit": int(limit) if limit is not None else None}


def write_scope(memory_home: Path, scope: dict[str, Any]) -> None:
    d = _state_dir(memory_home)
    d.mkdir(parents=True, exist_ok=True)
    (_state_dir(memory_home) / SCOPE_FILE).write_text(
        json.dumps(scope, indent=2) + "\n",
        encoding="utf-8",
    )


def recommend_scope(scan: dict[str, Any]) -> dict[str, Any] | None:
    """Auto scope when volume is small; None → ask user."""
    pending_90 = int(scan.get("pending_90d") or 0)
    if pending_90 == 0:
        return {"days": 90, "limit": None}
    if pending_90 <= AUTO_PENDING_90D_MAX:
        return dict(AUTO_SCOPE)
    if pending_90 >= ASK_PENDING_90D_MIN:
        return None
    return dict(AUTO_SCOPE)


def setup_hook_message(memory_home: Path) -> str:
    return SETUP_HOOK_MESSAGE.format(hub=str(memory_home.resolve()))


def scope_prompt(scan: dict[str, Any]) -> str:
    compact = {
        k: scan[k]
        for k in (
            "total_chats",
            "pending_90d",
            "pending_180d",
            "active_90d",
            "active_180d",
        )
        if k in scan
    }
    return SCOPE_PROMPT.format(
        pending_90d=scan.get("pending_90d", 0),
        total=scan.get("total_chats", 0),
        scan_json=json.dumps(compact, ensure_ascii=False),
    )


def ensure_hub(
    plugin_root: Path,
    memory_home: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Idempotent hub init (templates + anchor)."""
    if dry_run:
        return {"status": "dry_run", "memory_home": str(memory_home)}
    script = plugin_root / "scripts" / "init-memory.sh"
    if script.is_file():
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
    memory_home.mkdir(parents=True, exist_ok=True)
    persist_paths(plugin_root.resolve(), memory_home.resolve())
    return {"status": "ok", "via": "persist_paths"}


def _distill_with_fallback(
    row: dict[str, Any],
    *,
    memory_home: Path,
    projects_root: Path,
) -> dict[str, Any]:
    from lib.boundary_hooks import _load_distill_modules, distill_jsonl

    out = distill_jsonl(
        row["jsonl"],
        memory_home=memory_home,
        projects_root=projects_root,
        apply=True,
        bootstrap_decisions=True,
        event="first-run",
    )
    if out.get("status") == "distilled":
        return out
    try:
        extract_mod, _merge_mod = _load_distill_modules()
        extract = extract_mod.build_extract(
            row["jsonl"],
            projects_root=projects_root,
            strategy="auto",
            memory_home=memory_home,
        )
        slug = extract.get("workspace_slug") or row.get("project") or "project"
        project_path = memory_home / "chats" / "projects" / f"{slug}.md"
        apply_mechanical_auto_decisions(project_path, extract)
        return {
            "status": "auto_fallback",
            "chat_id": row["id"],
            "project": slug,
            "reason": out.get("status"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "chat_id": row["id"],
            "detail": str(exc),
        }


def run_distill_batch(
    memory_home: Path,
    scope: dict[str, Any],
    *,
    plugin_root: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict[str, Any]:
    days = int(scope.get("days", 90))
    limit = scope.get("limit")
    pending = list_chats_needing_distill(
        memory_home,
        projects_root=projects_root,
        days=days,
        limit=limit,
    )
    total = len(pending)
    distilled = 0
    auto_fallback = 0
    errors = 0
    details: list[dict[str, Any]] = []

    for i, row in enumerate(pending, start=1):
        out = _distill_with_fallback(
            row, memory_home=memory_home, projects_root=projects_root
        )
        details.append({"index": i, "total": total, **out})
        st = out.get("status")
        if st == "distilled":
            distilled += 1
        elif st == "auto_fallback":
            auto_fallback += 1
        elif st == "error":
            errors += 1

    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    gc = bootstrap_global_context(memory_home, manifest, dry_run=False)
    projects = int(gc.get("projects") or 0)

    return {
        "status": "ok",
        "scope": scope,
        "planned": total,
        "distilled": distilled,
        "auto_fallback": auto_fallback,
        "errors": errors,
        "projects": projects,
        "details": details,
        "plugin_root": str(plugin_root),
    }


def ready_message(stats: dict[str, Any]) -> str:
    return (
        f"[agent-memory] Ready: {stats.get('projects', 0)} projects, "
        f"{stats.get('distilled', 0)} distills"
        + (
            f" (+{stats.get('auto_fallback', 0)} [auto] fallback)"
            if stats.get("auto_fallback")
            else ""
        )
        + f". Hub: {stats.get('memory_home', '')}"
    )


def handle_first_run(
    *,
    memory_home: Path,
    plugin_root: Path | None = None,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
    script_file: str | Path | None = None,
) -> dict[str, Any] | None:
    """
    Returns first-run payload when bootstrap needed, else None.
    May set user_message for agent-orchestrated steps.
    """
    if is_initialized(memory_home):
        return None

    plugin = plugin_root or resolve_plugin_root(
        script_file=script_file or Path(__file__).resolve().parents[1] / "boundary-hooks.py",
        memory_home=memory_home,
    )
    if plugin is None:
        return {
            "first_run": "error",
            "user_message": "[agent-memory] Plugin root not found — run bash scripts/install-local.sh",
        }

    result: dict[str, Any] = {
        "first_run": "in_progress",
        "memory_home": str(memory_home.resolve()),
        "plugin_root": str(plugin.resolve()),
    }
    messages: list[str] = []

    ensure = ensure_hub(plugin, memory_home)
    result["init"] = ensure
    if ensure.get("status") == "error":
        result["user_message"] = "[agent-memory] init-memory failed — check Python and logs"
        return result

    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    if processed_by_id(manifest):
        gc = bootstrap_global_context(memory_home, manifest, dry_run=False)
        stats = {
            "memory_home": str(memory_home),
            "distilled": len(processed_by_id(manifest)),
            "projects": int(gc.get("projects") or 0),
            "skipped": "existing_manifest",
        }
        mark_initialized(memory_home, stats)
        result["first_run"] = "skipped_existing_data"
        messages.append(ready_message(stats))
        result["user_message"] = "\n\n".join(messages)
        return result

    scan = scan_chat_stats(memory_home, projects_root=projects_root)
    result["scan"] = scan
    messages.append(setup_hook_message(memory_home))
    result["first_run"] = "awaiting_setup"
    result["user_message"] = "\n\n".join(messages)
    return result
