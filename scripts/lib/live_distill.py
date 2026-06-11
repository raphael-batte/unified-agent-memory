"""Mid-session live distill — staging + manifest without project apply."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.chats_manifest import load_manifest
from lib.pending_chats import needs_distill


def should_live_distill(
    memory_home: Path,
    chat_id: str,
    jsonl: Path,
) -> bool:
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    return needs_distill(chat_id, jsonl, manifest)


def run_live_distill(
    distill_jsonl_fn,
    jsonl: Path,
    *,
    memory_home: Path,
    projects_root: Path,
    strategy: str = "auto",
) -> dict[str, Any]:
    """
    Live path: extract + merge staging/manifest/rolling, skip --apply to project .md.
    `distill_jsonl_fn` is boundary_hooks.distill_jsonl (injected to avoid cycles).
    """
    return distill_jsonl_fn(
        jsonl,
        memory_home=memory_home,
        projects_root=projects_root,
        strategy=strategy,
        apply=False,
        event="liveDistill",
    )
