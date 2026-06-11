"""Unified transcript access — Cursor jsonl first, generic role/content fallback."""

from __future__ import annotations

import re
from pathlib import Path

from lib import transcript_cursor as cursor
from lib import transcript_generic as generic
from lib.transcript_cursor import ParseStats, TranscriptSchemaError, workspace_slug

__all__ = [
    "ParseStats",
    "TranscriptSchemaError",
    "clear_transcript_cache",
    "extract_raw_user_texts",
    "find_transcript",
    "workspace_from_path",
    "workspace_slug",
]


def find_transcript(
    uuid: str,
    projects_root: Path,
    *,
    memory_home: Path | None = None,
    use_cache: bool = True,
) -> Path | None:
    needle = uuid.strip()
    path = cursor.find_transcript(needle, projects_root, use_cache=use_cache)
    if path is not None:
        return path

    # Hub fallback builds a path from the uuid — only allow a bare safe id so a
    # crafted uuid (e.g. "../../etc/x") cannot read files outside transcripts/.
    if memory_home is not None and re.fullmatch(r"[A-Za-z0-9._-]+", needle):
        hub = memory_home.expanduser().resolve()
        for candidate in (
            hub / "transcripts" / f"{needle}.jsonl",
            hub / "transcripts" / needle / f"{needle}.jsonl",
        ):
            if candidate.is_file():
                return candidate
    return None


def extract_raw_user_texts(jsonl: Path) -> tuple[list[str], ParseStats, str]:
    """
    Parse user messages. Returns (texts, stats, adapter_name).
    Tries Cursor schema, then generic role/content jsonl.
    """
    from lib.transcript_parse import parse_transcript

    parsed = parse_transcript(jsonl)
    if not parsed.user_messages:
        raise TranscriptSchemaError(
            f"no usable user messages in transcript: {jsonl}"
        )
    return parsed.user_texts(), parsed.stats, parsed.adapter


def workspace_from_path(jsonl: Path, projects_root: Path) -> str:
    ws = cursor.workspace_from_path(jsonl, projects_root)
    if ws != "unknown":
        return ws
    try:
        rel = jsonl.resolve().parts
        if "transcripts" in rel:
            idx = rel.index("transcripts")
            if idx + 1 < len(rel):
                return rel[idx + 1]
    except ValueError:
        pass
    return jsonl.parent.name or "imported"


def clear_transcript_cache() -> None:
    from lib.transcript_parse import clear_parse_cache

    cursor.clear_transcript_cache()
    clear_parse_cache()
