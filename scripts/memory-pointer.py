#!/usr/bin/env python3
"""Curate forward pointer (## Open threads) on project distill files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.chats_manifest import load_manifest, processed_by_id, save_manifest, upsert_processed  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.open_threads import collect_open_threads  # noqa: E402
from lib.pointer_provenance import (  # noqa: E402
    PROVENANCE_CURATED,
    format_curated_next_step,
    format_next_step_deprecated,
    strip_curated_marker,
)
from lib.project_merge import (  # noqa: E402
    LAST_UPDATED,
    _bullets,
    _format_bullets,
    _join_sections,
    _parse_sections,
    upsert_open_thread,
)
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
            f"## Next step\n\n{format_next_step_deprecated()}\n\n"
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


def _hub_skeleton(slug: str, day: str) -> str:
    return (
        f"# {slug}\n"
        f"_Last updated: {day}_\n\n"
        "## Summary\n\n\n"
        "## Decisions\n\n\n"
        f"## Next step\n\n{format_next_step_deprecated()}\n\n"
        "## Preferences\n\n\n"
        "## Open threads\n\n\n"
        "## Recent\n\n"
    )


def read_open_threads(project_path: Path) -> list[str]:
    if not project_path.is_file():
        return []
    _preamble, sections = _parse_sections(
        project_path.read_text(encoding="utf-8", errors="replace")
    )
    return _bullets(sections.get("Open threads", ""))


def add_open_thread(
    project_path: Path,
    label: str,
    text: str,
    *,
    memory_home: Path | None = None,
    cap: int = 7,
) -> dict:
    """Upsert a ``**[label]** text`` bullet into ## Open threads (curated, not distill)."""
    label = label.strip()
    body = text.strip()
    if not label:
        raise ValueError("label is empty")
    if not body:
        raise ValueError("thread text is empty")

    project_path.parent.mkdir(parents=True, exist_ok=True)
    day = now_iso()
    stamp = day[:10]  # tail-of-topic timestamp = today (date only)
    if project_path.is_file():
        raw = project_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw = _hub_skeleton(project_path.stem, day)

    if LAST_UPDATED.search(raw):
        raw = LAST_UPDATED.sub(f"_Last updated: {day}_", raw, count=1)

    preamble, sections = _parse_sections(raw)
    existing = _bullets(sections.get("Open threads", ""))
    updated = upsert_open_thread(existing, label, body, updated=stamp, cap=cap)
    sections["Open threads"] = _format_bullets(updated)
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

    return {
        "project_file": str(project_path),
        "label": label,
        "thread": body,
        "open_threads": updated,
        "count": len(updated),
    }


def cmd_add_thread(args: argparse.Namespace) -> int:
    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    project_path = _resolve_project_path(memory_home, args.project)
    text = args.text
    if text is None and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print("error: provide TEXT or stdin", file=sys.stderr)
        return 2
    try:
        result = add_open_thread(
            project_path, args.label, text, memory_home=memory_home
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    print(
        "warning: `set` is deprecated — use `add-thread <project> <label> \"…\"` "
        "for ## Open threads (forward pointer).",
        file=sys.stderr,
    )
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


def cmd_threads(args: argparse.Namespace) -> int:
    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    threads = collect_open_threads(
        memory_home, days=args.days, priority_slug=args.slug
    )
    print(
        json.dumps(
            {
                "memory_home": str(memory_home),
                "days": args.days,
                "count": len(threads),
                "threads": [t.to_dict() for t in threads],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
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
                "open_threads": read_open_threads(project_path),
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

    set_p = sub.add_parser(
        "set",
        help="[deprecated] Write curated ## Next step — prefer add-thread",
    )
    set_p.add_argument("project", help="Project slug or projects/foo.md")
    set_p.add_argument("text", nargs="?", help="Pointer text (or stdin)")
    set_p.set_defaults(func=cmd_set)

    thread_p = sub.add_parser(
        "add-thread", help="Upsert a direction bullet into ## Open threads"
    )
    thread_p.add_argument("project", help="Project slug or projects/foo.md")
    thread_p.add_argument("label", help="Direction label, e.g. sdm-ui")
    thread_p.add_argument("text", nargs="?", help="Thread text (or stdin)")
    thread_p.set_defaults(func=cmd_add_thread)

    threads_p = sub.add_parser(
        "threads", help="Rolling union of active Open threads across the whole hub"
    )
    threads_p.add_argument("--days", type=int, default=30, help="Window (default 30)")
    threads_p.add_argument("--slug", help="Current workspace slug — sorts first (hint)")
    threads_p.set_defaults(func=cmd_threads)

    show_p = sub.add_parser("show", help="Show Open threads (+ legacy Next step)")
    show_p.add_argument("project", help="Project slug or projects/foo.md")
    show_p.set_defaults(func=cmd_show)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
