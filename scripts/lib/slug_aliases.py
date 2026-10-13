"""Project slug aliases: one project, one file.

A renamed folder (``beta_app`` -> ``beta-app``) or a
renamed repo leaves its history in a second project file, and every new chat
lands in whichever name its workspace happens to carry. The hub config maps
the old names onto the canonical one::

    {"slug_aliases": {"beta_app": "beta-app"}}

``canonical_slug`` routes new distills to the canonical file; ``apply_merges``
folds the existing alias files into it once (``memory-doctor --merge-slugs``).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.hub_lock import hub_lock, write_atomic, write_json_atomic
from lib.markdown_sections import bullets, parse_sections
from lib.memory_config import load_hub_config
from lib.project_merge import _format_bullets, _join_sections

#: Sections whose bullets are unioned; anything else keeps the canonical text.
_BULLET_SECTIONS = ("Decisions", "Preferences", "Open threads", "Recent")
#: Retired sections are not carried into the canonical file.
_RETIRED_SECTIONS = ("Next step",)


def load_aliases(memory_home: Path) -> dict[str, str]:
    raw = load_hub_config(memory_home).get("slug_aliases") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for src, dst in raw.items():
        if isinstance(src, str) and isinstance(dst, str) and src.strip() and dst.strip():
            if src.strip().lower() != dst.strip().lower():
                out[src.strip().lower()] = dst.strip()
    return out


def canonical_slug(slug: str, memory_home: Path | None) -> str:
    """Follow alias links (at most a few hops, cycles stop)."""
    if memory_home is None or not slug:
        return slug
    aliases = load_aliases(memory_home)
    seen = {slug.lower()}
    current = slug
    for _ in range(5):
        nxt = aliases.get(current.lower())
        if not nxt or nxt.lower() in seen:
            break
        seen.add(nxt.lower())
        current = nxt
    return current


@dataclass
class MergePlan:
    src: str
    dst: str
    src_path: Path
    dst_path: Path
    added: dict[str, int] = field(default_factory=dict)
    archive: bool = False
    manifest_rows: int = 0
    queue_rows: int = 0


def _union(dst_items: list[str], src_items: list[str]) -> tuple[list[str], int]:
    seen = {i.strip() for i in dst_items}
    out = list(dst_items)
    added = 0
    for item in src_items:
        if item.strip() and item.strip() not in seen:
            out.append(item)
            seen.add(item.strip())
            added += 1
    return out, added


def _merged_text(dst_text: str, src_text: str) -> tuple[str, dict[str, int]]:
    dst_pre, dst_sec = parse_sections(dst_text)
    _src_pre, src_sec = parse_sections(src_text)
    added: dict[str, int] = {}
    for name, body in src_sec.items():
        if name in _RETIRED_SECTIONS:
            continue
        if name in _BULLET_SECTIONS:
            merged, n = _union(bullets(dst_sec.get(name, "")), bullets(body))
            if n:
                dst_sec[name] = _format_bullets(merged)
                added[name] = n
        elif not dst_sec.get(name, "").strip() and body.strip():
            dst_sec[name] = body
            added[name] = 1
    return _join_sections(dst_pre, dst_sec), added


def plan_merges(memory_home: Path) -> list[MergePlan]:
    projects = memory_home / "chats" / "projects"
    by_lower = {p.stem.lower(): p for p in projects.glob("*.md")}
    plans: list[MergePlan] = []
    for src_lower in sorted(load_aliases(memory_home)):
        src_path = by_lower.get(src_lower)
        if src_path is None:
            continue
        dst = canonical_slug(src_path.stem, memory_home)
        dst_path = by_lower.get(dst.lower(), projects / f"{dst}.md")
        if dst_path.resolve() == src_path.resolve():
            continue
        plan = MergePlan(src=src_path.stem, dst=dst_path.stem, src_path=src_path, dst_path=dst_path)
        if dst_path.is_file():
            _text, plan.added = _merged_text(
                dst_path.read_text(encoding="utf-8"), src_path.read_text(encoding="utf-8")
            )
        else:
            plan.added = {"(renamed)": 1}
        plan.archive = (memory_home / "chats" / "archive" / f"{plan.src}-decisions.md").is_file()
        src_rel = f"projects/{plan.src}.md"
        manifest = _read_json(memory_home / "chats" / "manifest.json", {})
        plan.manifest_rows = sum(
            1
            for e in manifest.get("processed") or []
            if any(str(t).lower() == src_rel.lower() for t in e.get("distilled_to") or [])
        )
        queue = _read_json(memory_home / ".state" / "pointer-curation-queue.json", [])
        plan.queue_rows = sum(
            1 for q in queue if isinstance(q, dict) and str(q.get("project_rel") or "").lower() == src_rel.lower()
        )
        plans.append(plan)
    return plans


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def apply_merges(memory_home: Path, plans: list[MergePlan]) -> dict[str, Any]:
    chats = memory_home / "chats"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # projects-backup-* is skipped by hub search and the pointer.
    backup = chats / f"projects-backup-merge-{stamp}"
    with hub_lock(memory_home, owner="doctor-merge-slugs"):
        for plan in plans:
            for path in (plan.src_path, plan.dst_path):
                if path.is_file():
                    target = backup / "projects" / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)

            src_text = plan.src_path.read_text(encoding="utf-8")
            if plan.dst_path.is_file():
                text, _added = _merged_text(plan.dst_path.read_text(encoding="utf-8"), src_text)
            else:
                text = src_text.replace(f"# {plan.src}\n", f"# {plan.dst}\n", 1)
            write_atomic(plan.dst_path, text)
            plan.src_path.unlink()

            src_arch = chats / "archive" / f"{plan.src}-decisions.md"
            if src_arch.is_file():
                dst_arch = chats / "archive" / f"{plan.dst}-decisions.md"
                (backup / "archive").mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_arch, backup / "archive" / src_arch.name)
                if dst_arch.is_file():
                    shutil.copy2(dst_arch, backup / "archive" / dst_arch.name)
                    dst_lines = dst_arch.read_text(encoding="utf-8").splitlines()
                    have = {ln.strip() for ln in dst_lines}
                    extra = [
                        ln for ln in src_arch.read_text(encoding="utf-8").splitlines()
                        if ln.strip().startswith("- ") and ln.strip() not in have
                    ]
                    write_atomic(dst_arch, "\n".join(dst_lines + extra).rstrip() + "\n")
                else:
                    write_atomic(dst_arch, src_arch.read_text(encoding="utf-8"))
                src_arch.unlink()

        renames = {f"projects/{p.src}.md".lower(): f"projects/{p.dst}.md" for p in plans}

        manifest_path = chats / "manifest.json"
        manifest = _read_json(manifest_path, None)
        if isinstance(manifest, dict):
            shutil.copy2(manifest_path, backup / "manifest.json")
            for entry in manifest.get("processed") or []:
                targets = entry.get("distilled_to")
                if not targets:
                    continue
                out: list[str] = []
                for t in targets:
                    t = renames.get(str(t).lower(), t)
                    if t not in out:
                        out.append(t)
                entry["distilled_to"] = out
            write_json_atomic(manifest_path, manifest)

        queue_path = memory_home / ".state" / "pointer-curation-queue.json"
        queue = _read_json(queue_path, None)
        if isinstance(queue, list):
            for q in queue:
                if isinstance(q, dict):
                    rel = str(q.get("project_rel") or "").lower()
                    if rel in renames:
                        q["project_rel"] = renames[rel]
                        q["workspace_slug"] = Path(renames[rel]).stem
            write_json_atomic(queue_path, queue)

    return {"merged": len(plans), "backup": str(backup)}
