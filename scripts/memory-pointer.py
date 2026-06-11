#!/usr/bin/env python3
"""Set or inspect curated ## Next step on a project distill file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.chats_manifest import load_manifest, processed_by_id, save_manifest, upsert_processed  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.pointer_provenance import PROVENANCE_CURATED, format_curated_next_step, strip_curated_marker  # noqa: E402
from lib.project_merge import LAST_UPDATED, _bullets, _join_sections, _parse_sections  # noqa: E402
from lib.secrets_guard import scan_file  # noqa: E402
from lib.timestamps import now_iso  # noqa: E402
from lib.transcript_cursor import safe_path_component  # noqa: E402


def _resolve_project_path(memory_home: Path, project: str) -> Path:
    raw = project.strip().lstrip("/")
    if raw.startswith("projects/"):
        rel = raw
    elif raw.endswith(".md"):
        rel = f"projects/{raw}"
    else:
        rel = f"projects/{safe_path_component(raw, fallback='project')}.md"
    return memory_home / "chats" / rel


def _project_rel(project_path: Path, memory_home: Path) -> str:
    try:
        return str(project_path.resolve().relative_to((memory_home / "chats").resolve()))
    except ValueError:
        return f"projects/{project_path.name}"


def read_pointer_bullet(project_path: Path) -> tuple[str | None, bool]:
    if not project_path.is_file():
        return None, False
    _preamble, sections = _parse_sections(
        project_path.read_text(encoding="utf-8", errors="replace")
    )
    for bullet in _bullets(sections.get("Next step", "")):
        curated = bullet.strip().lower().startswith("[curated]")
        text = strip_curated_marker(bullet)
        if text:
            return text, curated
    return None, False


def set_curated_pointer(
    project_path: Path,
    text: str,
    *,
    memory_home: Path | None = None,
) -> dict:
    body = text.strip()
    if not body:
        raise ValueError("pointer text is empty")

    project_path.parent.mkdir(parents=True, exist_ok=True)
    day = now_iso()
    if project_path.is_file():
        raw = project_path.read_text(encoding="utf-8", errors="replace")
    else:
        slug = project_path.stem
        raw = (
            f"# {slug}\n"
            f"_Last updated: {day}_\n\n"
            "## Summary\n\n\n"
            "## Decisions\n\n\n"
            "## Next step\n\n\n"
            "## Preferences\n\n\n"
            "## Open threads\n\n\n"
            "## Recent\n\n"
        )

    if LAST_UPDATED.search(raw):
        raw = LAST_UPDATED.sub(f"_Last updated: {day}_", raw, count=1)

    preamble, sections = _parse_sections(raw)
    sections["Next step"] = format_curated_next_step(body)
    merged = _join_sections(preamble, sections)

    tmp = project_path.with_suffix(".md.tmpcheck")
    tmp.write_text(merged, encoding="utf-8")
    try:
        hits = scan_file(tmp)
        if hits:
            raise ValueError(f"refusing to write — secrets detected: {hits[0]}")
    finally:
        tmp.unlink(missing_ok=True)

    project_path.write_text(merged, encoding="utf-8")

    updated_manifest = 0
    if memory_home is not None:
        manifest_path = memory_home / "chats" / "manifest.json"
        manifest = load_manifest(manifest_path)
        rel = _project_rel(project_path, memory_home)
        for entry in processed_by_id(manifest).values():
            targets = entry.get("distilled_to") or []
            if rel not in targets:
                continue
            upsert_processed(
                manifest,
                {
                    **entry,
                    "pointer_source": PROVENANCE_CURATED,
                    "pointer_set_at": day,
                },
            )
            updated_manifest += 1
        if updated_manifest:
            save_manifest(manifest_path, manifest)

    return {
        "project_file": str(project_path),
        "pointer": body,
        "curated": True,
        "manifest_entries_updated": updated_manifest,
    }


def cmd_set(args: argparse.Namespace) -> int:
    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    project_path = _resolve_project_path(memory_home, args.project)
    text = args.text
    if text is None and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print("error: provide TEXT or stdin", file=sys.stderr)
        return 2
    result = set_curated_pointer(project_path, text, memory_home=memory_home)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    project_path = _resolve_project_path(memory_home, args.project)
    text, curated = read_pointer_bullet(project_path)
    print(
        json.dumps(
            {
                "project_file": str(project_path),
                "pointer": text,
                "curated": curated,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home", help="Hub path override")
    sub = parser.add_subparsers(dest="command", required=True)

    set_p = sub.add_parser("set", help="Write curated ## Next step")
    set_p.add_argument("project", help="Project slug or projects/foo.md")
    set_p.add_argument("text", nargs="?", help="Pointer text (or stdin)")
    set_p.set_defaults(func=cmd_set)

    show_p = sub.add_parser("show", help="Show current Next step")
    show_p.add_argument("project", help="Project slug or projects/foo.md")
    show_p.set_defaults(func=cmd_show)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
