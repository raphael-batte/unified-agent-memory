#!/usr/bin/env python3
"""Map-reduce distill — agent map per window, script reduce into staging."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.distill_map import (  # noqa: E402
    build_map_staging_markdown,
    map_staging_path,
    run_reduce,
    write_map_staging,
)
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.transcript import find_transcript  # noqa: E402

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"


def load_extract(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uuid", help="Chat uuid")
    parser.add_argument("--memory-home", help="Hub path")
    parser.add_argument("--extract", metavar="JSON", help="Existing extract file")
    parser.add_argument("--map-staging", metavar="MD", help="Map staging for --reduce")
    parser.add_argument("--reduce", action="store_true", help="Reduce filled map staging")
    parser.add_argument("--projects-root", metavar="DIR")
    args = parser.parse_args()

    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    chat_id = args.uuid.strip()

    if args.extract:
        extract = load_extract(Path(args.extract).expanduser().resolve())
    else:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "distill_extract_mod", SCRIPT_DIR / "distill-extract.py"
        )
        if spec is None or spec.loader is None:
            print("Error: distill-extract unavailable", file=sys.stderr)
            return 1
        de = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(de)
        projects_root = (
            Path(args.projects_root).expanduser().resolve()
            if args.projects_root
            else DEFAULT_PROJECTS_ROOT
        )
        jsonl = find_transcript(chat_id, projects_root, memory_home=memory_home)
        if jsonl is None:
            print(f"Error: transcript not found: {chat_id}", file=sys.stderr)
            return 1
        extract = de.build_extract(
            jsonl, projects_root=projects_root, memory_home=memory_home
        )

    if args.reduce:
        map_path = (
            Path(args.map_staging).expanduser().resolve()
            if args.map_staging
            else map_staging_path(memory_home, extract)
        )
        if not map_path.is_file():
            print(f"Error: map staging not found: {map_path}", file=sys.stderr)
            return 1
        try:
            reduce_path = run_reduce(memory_home, extract, map_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"reduce_staging": str(reduce_path)}, indent=2))
        return 0

    path = write_map_staging(memory_home, extract)
    if path is None:
        md = build_map_staging_markdown(extract)
        fallback = map_staging_path(memory_home, extract)
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(md, encoding="utf-8")
        path = fallback
    print(json.dumps({"map_staging": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
