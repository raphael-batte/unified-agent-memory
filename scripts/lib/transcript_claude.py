"""Claude Code jsonl adapter.

Claude Code writes ``<projects_root>/<encoded-cwd>/<session-id>.jsonl``. Conversation rows
carry the role under ``message.role`` with ``type`` at the top level, alongside bookkeeping
rows (``queue-operation``, ``attachment``, …) that are not part of the conversation.

Rather than duplicate the parser, :func:`normalize_rows` rewrites conversation rows into the
``{"role": …, "message": {"content": [blocks]}}`` shape the Cursor parser already understands,
so tool calls and TodoWrite reconstruction come for free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.transcript_cursor import ParseStats, TranscriptSchemaError

__all__ = [
    "NOISE_TYPES",
    "build_transcript_index",
    "clear_transcript_cache",
    "extract_raw_user_texts",
    "find_transcript",
    "is_claude_row",
    "is_sidechain",
    "looks_like_claude",
    "normalize_rows",
    "workspace_from_row",
]

#: Bookkeeping rows Claude Code appends alongside the conversation.
NOISE_TYPES: frozenset[str] = frozenset(
    {
        "queue-operation",
        "attachment",
        "last-prompt",
        "summary",
        "file-history-snapshot",
        "system",
        "progress",
    }
)

_CONVERSATION_TYPES: frozenset[str] = frozenset({"user", "assistant"})


def is_claude_row(obj: Any) -> bool:
    """True for a conversation row in Claude Code shape (role nested under ``message``)."""
    if not isinstance(obj, dict):
        return False
    if obj.get("type") not in _CONVERSATION_TYPES:
        return False
    if "role" in obj:
        # Cursor rows put the role at the top level — not ours.
        return False
    message = obj.get("message")
    return isinstance(message, dict) and "content" in message


def looks_like_claude(objects: list[dict[str, Any]]) -> bool:
    return any(is_claude_row(obj) for obj in objects)


def is_sidechain(obj: dict[str, Any]) -> bool:
    """Subagent rows — real work, but not this conversation's history."""
    return bool(obj.get("isSidechain"))


def _content_blocks(content: Any) -> list[dict[str, Any]]:
    """Normalize ``message.content`` (str or block list) to text/tool_use blocks."""
    if isinstance(content, str):
        text = content.strip()
        return [{"type": "text", "text": text}] if text else []
    if not isinstance(content, list):
        return []

    blocks: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text = str(block.get("text") or "").strip()
            if text:
                blocks.append({"type": "text", "text": text})
        elif kind == "tool_use":
            blocks.append(block)
        # tool_result / thinking / image blocks carry no distillable prose.
    return blocks


def normalize_rows(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite Claude rows into the Cursor row shape; drop noise and sidechains."""
    rows: list[dict[str, Any]] = []
    for obj in objects:
        if not is_claude_row(obj) or is_sidechain(obj):
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in _CONVERSATION_TYPES:
            continue
        blocks = _content_blocks(message.get("content"))
        if not blocks:
            continue
        row: dict[str, Any] = {"role": role, "message": {"content": blocks}}
        for key in ("timestamp", "sessionId", "cwd", "gitBranch", "uuid"):
            if obj.get(key) is not None:
                row[key] = obj[key]
        rows.append(row)
    return rows


def workspace_from_row(obj: dict[str, Any]) -> str | None:
    cwd = obj.get("cwd")
    return cwd.strip() if isinstance(cwd, str) and cwd.strip() else None


def extract_raw_user_texts(jsonl: Path) -> tuple[list[str], ParseStats]:
    """Parse a Claude Code transcript — raw user text before secret sanitization."""
    from lib.transcript_parse import parse_transcript

    parsed = parse_transcript(jsonl)
    if parsed.adapter != "claude":
        raise TranscriptSchemaError(f"not a Claude Code transcript: {jsonl}")
    if not parsed.user_messages:
        raise TranscriptSchemaError(f"no usable user messages in transcript: {jsonl}")
    return parsed.user_texts(), parsed.stats


# --- discovery -------------------------------------------------------------
# Flat layout: <projects_root>/<encoded-cwd>/<session-id>.jsonl

_INDEX_CACHE: dict[str, tuple[float, dict[str, Path]]] = {}


def _index_mtime(projects_root: Path) -> float:
    if not projects_root.is_dir():
        return 0.0
    try:
        return projects_root.stat().st_mtime
    except OSError:
        return 0.0


def build_transcript_index(projects_root: Path) -> dict[str, Path]:
    """Map session id -> newest jsonl path."""
    index: dict[str, Path] = {}
    if not projects_root.is_dir():
        return index
    for jsonl in projects_root.glob("*/*.jsonl"):
        uid = jsonl.stem
        prev = index.get(uid)
        if prev is None or jsonl.stat().st_mtime >= prev.stat().st_mtime:
            index[uid] = jsonl
    return index


def find_transcript(
    uuid: str,
    projects_root: Path,
    *,
    use_cache: bool = True,
) -> Path | None:
    needle = uuid.strip()
    if not needle or not projects_root.is_dir():
        return None

    root_key = str(projects_root.resolve())
    mtime = _index_mtime(projects_root)

    if use_cache and root_key in _INDEX_CACHE:
        cached_mtime, cached_index = _INDEX_CACHE[root_key]
        if cached_mtime == mtime:
            return cached_index.get(needle)

    index = build_transcript_index(projects_root)
    _INDEX_CACHE[root_key] = (mtime, index)
    return index.get(needle)


def clear_transcript_cache() -> None:
    _INDEX_CACHE.clear()
