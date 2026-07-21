#!/usr/bin/env python3
"""List agent chat transcripts (all environments) vs MEMORY_HOME/chats/manifest.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.chats_manifest import load_manifest, processed_by_id
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.pending_chats import needs_distill, scan_transcript_rows  # noqa: E402
from lib.timestamps import transcript_is_newer_than_distill  # noqa: E402
from lib.transcript_cursor import TranscriptSchemaError  # noqa: E402
from lib.transcript_parse import parse_transcript  # noqa: E402


def first_user_query(jsonl: Path) -> str:
    """First real user message — via the shared parser, so any environment works."""
    try:
        texts = parse_transcript(jsonl).user_texts()
    except (TranscriptSchemaError, OSError):
        return "(no user text)"
    return texts[0][:140] if texts else "(no user text)"


def scan_transcripts(projects_root: Path | None = None) -> list[dict]:
    """Newest-first inventory across every installed environment."""
    rows = []
    for row in scan_transcript_rows(projects_root):
        jsonl = row["jsonl"]
        rows.append(
            {
                "id": row["id"],
                "project": row["project"],
                "workspace": row["workspace"],
                "env": row["env"],
                "date": row["date"],
                "size": jsonl.stat().st_size,
                "path": row["path"],
                "first_query": first_user_query(jsonl),
            }
        )
    return rows


def chat_counts(memory_home: Path, projects_root: Path | None = None) -> tuple[int, int, int]:
    """Return (processed, pending, total)."""
    manifest_path = memory_home / "chats" / "manifest.json"
    rows = scan_transcripts(projects_root)
    total = len(rows)
    if not manifest_path.is_file():
        return 0, total, total
    manifest = load_manifest(manifest_path)
    processed_ids = set(processed_by_id(manifest))
    # Same gate the distill itself uses. Counting "absent from the manifest"
    # instead reported a smaller number than `sync-memory`, because a chat that
    # grew new messages since its distill is already in the manifest — two
    # counters disagreeing is how a status line stops being trusted.
    pending = sum(1 for r in rows if needs_distill(r["id"], Path(r["path"]), manifest))
    return len(processed_ids), pending, total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--memory-home", metavar="PATH")
    parser.add_argument("--projects-root", metavar="DIR")
    parser.add_argument(
        "--json", action="store_true", help="Machine-readable inventory on stdout"
    )
    args = parser.parse_args()

    mem = resolve_memory_home(args.memory_home, script_file=__file__)
    projects_root = (
        Path(args.projects_root).expanduser().resolve()
        if args.projects_root
        else None  # None = scan every installed environment
    )
    manifest_path = mem / "chats/manifest.json"

    if args.json:
        processed_ids = (
            set(processed_by_id(load_manifest(manifest_path)))
            if manifest_path.exists()
            else set()
        )
        rows = scan_transcripts(projects_root)
        if args.pending:
            rows = [r for r in rows if r["id"] not in processed_ids]
        for row in rows:
            row["distilled"] = row["id"] in processed_ids
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

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
