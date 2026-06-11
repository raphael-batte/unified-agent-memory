#!/usr/bin/env python3
"""Search agent-memory hub — BM25-lite over bullets and optional extracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.hub_search import search_hub  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402


def _parse_layers(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    allowed = {"chats", "context", "feedback", "extract"}
    bad = parts - allowed
    if bad:
        raise ValueError(f"unknown layers: {', '.join(sorted(bad))}")
    return parts


def format_text_report(data: dict) -> str:
    lines = [f"Search: {data.get('query', '')!r}"]
    if data.get("warning"):
        lines.append(f"Warning: {data['warning']}")
    meta = data.get("meta") or {}
    lines.append(
        f"Corpus: {meta.get('hub_docs', 0)} hub docs"
        + (
            f", {meta.get('extract_docs', 0)} extract snippets"
            if meta.get("extract_docs") is not None
            else ""
        )
    )
    hits = data.get("hits") or []
    if not hits:
        lines.append("No hits.")
        return "\n".join(lines)
    for idx, hit in enumerate(hits, 1):
        drill = hit.get("drill") or ""
        drill_bit = f" drill={drill}" if drill else ""
        lines.append(
            f"{idx}. [{hit.get('score')}] {hit.get('layer')} "
            f"{hit.get('path')}#{hit.get('section')} "
            f"({hit.get('date') or '?'}){drill_bit}\n"
            f"   {hit.get('text', '')[:200]}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Search terms")
    parser.add_argument("--memory-home", help="Hub path override")
    parser.add_argument(
        "--layer",
        dest="layers",
        help="Comma-separated: chats, context, feedback, extract",
    )
    parser.add_argument("--top", type=int, default=8, help="Max results (default 8)")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Include chats/extracts/*.json within retention_days",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        help="Deep search window (= hub retention default)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    memory_home = resolve_memory_home(
        args.memory_home, script_file=str(SCRIPT_DIR / "memory-search.py")
    )
    try:
        layer_set = _parse_layers(args.layers)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = search_hub(
        memory_home,
        args.query,
        top=args.top,
        layers=layer_set,
        deep=args.deep,
        retention_days=args.retention_days,
    )

    if args.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_text_report(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
