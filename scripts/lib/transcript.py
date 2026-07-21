"""Unified transcript access — Cursor jsonl first, generic role/content fallback."""

from __future__ import annotations

import re
from pathlib import Path

from lib import transcript_claude as claude
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
    projects_root: Path | None = None,
    *,
    memory_home: Path | None = None,
    use_cache: bool = True,
) -> Path | None:
    """Locate a transcript in any installed environment.

    ``projects_root=None`` searches every environment at its own root. An explicit
    root is probed with each environment's indexer — the layouts are disjoint, so at
    most one matches and existing callers keep working unchanged.
    """
    from lib import envs

    needle = uuid.strip()
    if not needle:
        return None

    if projects_root is not None:
        targets = [(env, projects_root) for env in envs.all_envs()]
    else:
        targets = [(env, env.transcript_root()) for env in envs.available_envs()]

    for env, root in targets:
        path = env.find_transcript(needle, root, use_cache=use_cache)
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


def workspace_from_path(jsonl: Path, projects_root: Path | None = None) -> str:
    """Workspace id owning this transcript.

    ``projects_root=None`` tries every installed environment's root. Claude's flat
    layout needs no nesting rule — it falls through to the parent directory name,
    which is exactly its encoded workspace path.
    """
    from lib import envs

    roots = (
        [projects_root]
        if projects_root is not None
        else [env.transcript_root() for env in envs.available_envs()]
    )
    for root in roots:
        ws = cursor.workspace_from_path(jsonl, root)
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
    claude.clear_transcript_cache()
    clear_parse_cache()
