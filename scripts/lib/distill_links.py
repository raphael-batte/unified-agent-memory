"""Chat links in distill output — Cursor markdown [title](uuid)."""

from __future__ import annotations

import re
from pathlib import Path

from lib.transcript import find_transcript

_LINK_UNSAFE = re.compile(r"[\[\]\(\)]")


def chat_link_title(extract: dict, *, max_len: int = 48) -> str:
    """Short label for markdown link text."""
    raw = (extract.get("first_query") or extract.get("uuid") or "chat").strip()
    raw = _LINK_UNSAFE.sub("", raw)
    raw = re.sub(r"\s+", " ", raw)
    if len(raw) <= max_len:
        return raw or "chat"
    return raw[: max_len - 3].rstrip() + "..."


def transcript_available(
    extract: dict,
    *,
    memory_home: Path | None = None,
    projects_root: Path | None = None,
) -> bool:
    """True if full chat transcript is still on disk."""
    source = extract.get("source_path")
    if isinstance(source, str) and source.strip():
        if Path(source).expanduser().is_file():
            return True
    uid = extract.get("uuid")
    if not isinstance(uid, str) or not uid.strip():
        return False
    if projects_root is None:
        projects_root = Path.home() / ".cursor/projects"
    return (
        find_transcript(uid.strip(), projects_root, memory_home=memory_home)
        is not None
    )


def format_chat_markdown_link(extract: dict) -> str | None:
    """Return [title](uuid) when transcript exists."""
    if not extract.get("transcript_available"):
        return None
    uid = extract.get("uuid")
    if not isinstance(uid, str) or not uid.strip():
        return None
    title = chat_link_title(extract)
    return f"[{title}]({uid.strip()})"


def enrich_extract(
    extract: dict,
    *,
    memory_home: Path | None = None,
    projects_root: Path | None = None,
) -> dict:
    """Add transcript_available flag (does not mutate input)."""
    out = dict(extract)
    out["transcript_available"] = transcript_available(
        out, memory_home=memory_home, projects_root=projects_root
    )
    return out


def recent_bullet(extract: dict, day: str) -> str:
    """Recent line with optional chat link prefix."""
    link = format_chat_markdown_link(extract)
    uid = str(extract.get("uuid", "?"))[:8]
    count = extract.get("user_message_count", "?")
    strategy = extract.get("strategy", "?")
    keywords = ", ".join(extract.get("keywords_hit") or []) or "—"
    meta = f"({count} msgs, strategy={strategy}, keywords: {keywords})"
    if link:
        return f"{day}: distilled {link} {meta}"
    return (
        f"{day}: distilled from chat `{uid}…` {meta} (transcript archived)"
    )
