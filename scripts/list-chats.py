#!/usr/bin/env python3
"""List Cursor chat transcripts vs MEMORY_HOME/chats/manifest.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.chats_manifest import load_manifest, processed_by_id  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.timestamps import transcript_is_newer_than_distill  # noqa: E402
from lib.transcript_cursor import (  # noqa: E402
    build_transcript_index,
    normalize_user_text,
    workspace_slug,
)

PROJECTS_ROOT = Path.home() / ".cursor/projects"


def first_user_query(jsonl: Path) -> str:
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("role") != "user":
            continue
        for block in obj.get("message", {}).get("content", []):
            if block.get("type") != "text":
                continue
            text = normalize_user_text(block.get("text", ""))
            if text and not text.startswith("["):
                return text[:140]
    return "(no user text)"


def scan_transcripts(projects_root: Path = PROJECTS_ROOT) -> list[dict]:
    rows = []
    index = build_transcript_index(projects_root)
    for chat_id, jsonl in sorted(index.items(), key=lambda kv: kv[1].stat().st_mtime, reverse=True):
        if "/subagents/" in str(jsonl):
            continue
        workspace = jsonl.parts[-4] if len(jsonl.parts) >= 4 else "unknown"
        st = jsonl.stat()
        rows.append(
            {
                "id": chat_id,
                "project": workspace_slug(workspace),
                "workspace": workspace,
                "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
                "size": st.st_size,
                "path": str(jsonl),
                "first_query": first_user_query(jsonl),
            }
        )
    return rows


def chat_counts(memory_home: Path, projects_root: Path = PROJECTS_ROOT) -> tuple[int, int, int]:
    """Return (processed, pending, total)."""
    manifest_path = memory_home / "chats" / "manifest.json"
    rows = scan_transcripts(projects_root)
    total = len(rows)
    if not manifest_path.is_file():
        return 0, total, total
    manifest = load_manifest(manifest_path)
    processed_ids = set(processed_by_id(manifest))
    pending = sum(1 for r in rows if r["id"] not in processed_ids)
    return len(processed_ids), pending, total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--memory-home", metavar="PATH")
    parser.add_argument("--projects-root", metavar="DIR")
    args = parser.parse_args()

    mem = resolve_memory_home(args.memory_home, script_file=__file__)
    projects_root = (
        Path(args.projects_root).expanduser().resolve()
        if args.projects_root
        else PROJECTS_ROOT
    )
    manifest_path = mem / "chats/manifest.json"

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        print("Run: bash scripts/init-memory.sh (from agent-memory repo)")
        return

    manifest = load_manifest(manifest_path)
    processed_map = processed_by_id(manifest)
    processed_ids = set(processed_map)
    rows = scan_transcripts(projects_root)

    if args.pending:
        rows = [r for r in rows if r["id"] not in processed_ids]
        print(f"Pending distill ({len(rows)} chats)")
        print(f"  MEMORY_HOME: {mem}")
        print(f"  manifest: {manifest_path}\n")
    elif args.all:
        print(f"All parent chats ({len(rows)})")
        print(f"  MEMORY_HOME: {mem}\n")
    else:
        pending = [r for r in rows if r["id"] not in processed_ids]
        print(f"MEMORY_HOME: {mem}")
        print(f"Processed: {len(processed_ids)}  Pending: {len(pending)}  Total: {len(rows)}")
        print("Run with --pending or --all")
        return

    for r in rows:
        entry = processed_map.get(r["id"])
        if entry:
            distilled = entry.get("distilled_at", "?")
            jsonl = Path(r["path"])
            stale = (
                transcript_is_newer_than_distill(jsonl, distilled)
                if distilled != "?"
                else False
            )
            flag = " STALE" if stale else ""
            status = f"done ({distilled}){flag}"
        else:
            status = "PENDING"
        print(f"{r['date']}  [{status}]  {r['project']}")
        print(f"  id: {r['id']}")
        print(f"  {r['first_query']}")
        print()


if __name__ == "__main__":
    main()
