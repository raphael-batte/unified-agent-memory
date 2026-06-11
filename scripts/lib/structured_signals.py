"""Structured transcript signals for pointer extraction (TodoWrite state)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lib.secrets_guard import sanitize_message
from lib.transcript_parse import ParsedTranscript, TodoItem

MIN_TODO_POINTER_LEN = 12
TODO_POINTER_CONFIDENCE = 0.90
TODO_POINTER_SOURCE = "todo_state"


def _clean_todo_text(text: str) -> str | None:
    line = re.sub(r"\s+", " ", text.strip())
    if len(line) < MIN_TODO_POINTER_LEN:
        return None
    clean, _n = sanitize_message(line)
    return clean


@dataclass(frozen=True)
class TodoPointerSignal:
    text: str
    source: str = TODO_POINTER_SOURCE
    confidence: float = TODO_POINTER_CONFIDENCE


def _pick_todo(todos: list[TodoItem]) -> TodoItem | None:
    for item in todos:
        if item.status == "in_progress" and item.content.strip():
            return item
    for item in todos:
        if item.status == "pending" and item.content.strip():
            return item
    return None


def _todo_items_from_extract(extract: dict) -> list[TodoItem]:
    raw = extract.get("open_todos") or []
    out: list[TodoItem] = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").strip()
        status = str(row.get("status") or "pending")
        tid = row.get("id")
        out.append(TodoItem(content=content, status=status, id=str(tid) if tid else None))
    return out


def todo_pointer_from_parsed(parsed: ParsedTranscript) -> TodoPointerSignal | None:
    """Open TodoWrite item as next-step signal; skip when all todos completed."""
    if parsed.all_todos_completed:
        return None
    picked = _pick_todo(parsed.open_todos())
    if picked is None:
        return None
    clean = _clean_todo_text(picked.content)
    if not clean:
        return None
    return TodoPointerSignal(text=clean)


def todo_pointer_from_extract(extract: dict) -> TodoPointerSignal | None:
    if extract.get("all_todos_completed"):
        return None
    picked = _pick_todo(_todo_items_from_extract(extract))
    if picked is None:
        return None
    clean = _clean_todo_text(picked.content)
    if not clean:
        return None
    return TodoPointerSignal(text=clean)
