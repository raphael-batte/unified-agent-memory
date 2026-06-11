"""Single-pass Cursor/generic jsonl transcript parser."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.secrets_guard import sanitize_message
from lib.transcript_cursor import (
    ParseStats,
    TranscriptSchemaError,
    is_redacted_or_noise,
    normalize_user_text,
)
from lib.transcript_generic import _text_from_obj as generic_user_text


@dataclass(frozen=True)
class Msg:
    text: str
    index: int
    timestamp: str | None = None
    role: str = "user"


@dataclass(frozen=True)
class ToolCall:
    name: str
    args_preview: str
    index: int
    timestamp: str | None = None


@dataclass(frozen=True)
class TodoItem:
    content: str
    status: str
    id: str | None = None


@dataclass
class ParsedTranscript:
    user_messages: list[Msg]
    assistant_blocks: list[Msg]
    tool_calls: list[ToolCall]
    todos: list[TodoItem]
    source_path: Path
    stats: ParseStats
    adapter: str = "cursor"
    _all_todos_completed: bool = field(default=False, repr=False)

    def user_texts(self) -> list[str]:
        return [m.text for m in self.user_messages]

    def last_user_text(self) -> str | None:
        if not self.user_messages:
            return None
        clean, _n = sanitize_message(self.user_messages[-1].text)
        return clean

    def assistant_text_tail(self, *, tail_rows: int = 12) -> list[str]:
        blocks = [m.text for m in self.assistant_blocks]
        return blocks[-tail_rows:]

    @property
    def all_todos_completed(self) -> bool:
        return self._all_todos_completed

    def open_todos(self) -> list[TodoItem]:
        return [
            t
            for t in self.todos
            if t.status in ("pending", "in_progress") and t.content.strip()
        ]

    def last_assistant_summary(self, *, max_len: int = 600) -> str | None:
        """Last assistant text block — prefer longest paragraph (substance over sign-off)."""
        for block in reversed(self.assistant_blocks):
            text = block.text.strip()
            if not text:
                continue
            paras = [p.strip() for p in text.split("\n\n") if p.strip()]
            summary = max(paras, key=len) if paras else text
            summary = re.sub(r"\s+", " ", summary).strip()
            clean, _n = sanitize_message(summary)
            if not clean:
                continue
            if len(clean) > max_len:
                clean = clean[: max_len - 3].rstrip() + "..."
            return clean
        return None


_PARSE_CACHE: dict[str, tuple[float, ParsedTranscript]] = {}


def clear_parse_cache() -> None:
    _PARSE_CACHE.clear()


def _row_timestamp(obj: dict[str, Any]) -> str | None:
    for key in ("timestamp", "created_at", "createdAt", "time"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _read_objects(jsonl: Path) -> tuple[list[dict[str, Any]], int]:
    if not jsonl.is_file():
        raise TranscriptSchemaError(f"transcript not found: {jsonl}")
    objects: list[dict[str, Any]] = []
    lines_read = 0
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        lines_read += 1
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            objects.append(obj)
    if lines_read == 0:
        raise TranscriptSchemaError(f"empty transcript: {jsonl}")
    return objects, lines_read


def _assistant_text_from_obj(obj: dict[str, Any]) -> str | None:
    if obj.get("role") != "assistant":
        return None
    parts: list[str] = []
    for block in obj.get("message", {}).get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = str(block.get("text", "")).strip()
        if text and not is_redacted_or_noise(text):
            parts.append(text)
    if not parts:
        return None
    return "\n".join(parts)


def _tool_calls_from_obj(obj: dict[str, Any], index: int) -> list[ToolCall]:
    if obj.get("role") != "assistant":
        return []
    ts = _row_timestamp(obj)
    out: list[ToolCall] = []
    for block in obj.get("message", {}).get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "tool")
        inp = block.get("input")
        if isinstance(inp, dict):
            preview = json.dumps(inp, ensure_ascii=False)[:240]
        else:
            preview = str(inp or "")[:240]
        out.append(ToolCall(name=name, args_preview=preview, index=index, timestamp=ts))
    return out


def _todo_writes_from_obj(obj: dict[str, Any]) -> list[dict[str, Any]]:
    if obj.get("role") != "assistant":
        return []
    writes: list[dict[str, Any]] = []
    for block in obj.get("message", {}).get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        if block.get("name") != "TodoWrite":
            continue
        inp = block.get("input")
        if isinstance(inp, dict):
            writes.append(inp)
    return writes


def _reconstruct_todos(writes: list[dict[str, Any]]) -> tuple[list[TodoItem], bool]:
    state: dict[str, TodoItem] = {}
    order: list[str] = []

    for call in writes:
        todos = call.get("todos")
        if not isinstance(todos, list):
            continue
        merge = bool(call.get("merge"))
        if not merge:
            state.clear()
            order.clear()
        for raw in todos:
            if not isinstance(raw, dict):
                continue
            tid = str(raw.get("id") or f"todo-{len(order)}")
            status = str(raw.get("status") or "pending")
            content = raw.get("content")
            if merge and tid in state:
                prev = state[tid]
                text = prev.content if content is None else str(content)
            else:
                text = "" if content is None else str(content)
            state[tid] = TodoItem(content=text.strip(), status=status, id=tid)
            if tid not in order:
                order.append(tid)

    items = [state[i] for i in order if i in state]
    all_completed = bool(items) and all(
        t.status in ("completed", "cancelled") for t in items
    )
    return items, all_completed


def _parse_cursor_objects(
    objects: list[dict[str, Any]],
    *,
    lines_read: int,
    source_path: Path,
) -> ParsedTranscript:
    stats = ParseStats(lines_read=lines_read)
    user_messages: list[Msg] = []
    assistant_blocks: list[Msg] = []
    tool_calls: list[ToolCall] = []
    todo_writes: list[dict[str, Any]] = []

    for index, obj in enumerate(objects):
        stats.json_lines += 1
        ts = _row_timestamp(obj)
        role = obj.get("role")

        if role == "user":
            stats.user_rows += 1
            for block in obj.get("message", {}).get("content", []):
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                stats.text_blocks += 1
                text = normalize_user_text(str(block.get("text", "")))
                if is_redacted_or_noise(text):
                    continue
                user_messages.append(Msg(text=text, index=index, timestamp=ts, role="user"))

        elif role == "assistant":
            blob = _assistant_text_from_obj(obj)
            if blob:
                assistant_blocks.append(
                    Msg(text=blob, index=index, timestamp=ts, role="assistant")
                )
            tool_calls.extend(_tool_calls_from_obj(obj, index))
            todo_writes.extend(_todo_writes_from_obj(obj))

    if stats.json_lines == 0:
        raise TranscriptSchemaError(f"no JSON lines in transcript: {source_path}")
    if not user_messages and not assistant_blocks and not tool_calls:
        if stats.user_rows == 0:
            raise TranscriptSchemaError(f"no user role rows: {source_path}")
        raise TranscriptSchemaError(
            f"only redacted/noise user messages in transcript: {source_path}"
        )
    if stats.user_rows > 0 and stats.text_blocks == 0 and not user_messages:
        raise TranscriptSchemaError(
            f"no text content blocks in user messages: {source_path}"
        )

    todos, all_done = _reconstruct_todos(todo_writes)
    return ParsedTranscript(
        user_messages=user_messages,
        assistant_blocks=assistant_blocks,
        tool_calls=tool_calls,
        todos=todos,
        source_path=source_path,
        stats=stats,
        adapter="cursor",
        _all_todos_completed=all_done,
    )


def _parse_generic_objects(
    objects: list[dict[str, Any]],
    *,
    lines_read: int,
    source_path: Path,
) -> ParsedTranscript:
    stats = ParseStats(lines_read=lines_read)
    user_messages: list[Msg] = []

    for index, obj in enumerate(objects):
        stats.json_lines += 1
        raw = generic_user_text(obj)
        if raw is None:
            continue
        stats.user_rows += 1
        stats.text_blocks += 1
        if is_redacted_or_noise(raw):
            continue
        user_messages.append(
            Msg(
                text=raw,
                index=index,
                timestamp=_row_timestamp(obj),
                role="user",
            )
        )

    if stats.json_lines == 0:
        raise TranscriptSchemaError(f"no JSON lines (not generic format?): {source_path}")
    if stats.user_rows == 0:
        raise TranscriptSchemaError(f"no user/human rows: {source_path}")
    if not user_messages:
        raise TranscriptSchemaError(f"only empty/noise user rows: {source_path}")

    return ParsedTranscript(
        user_messages=user_messages,
        assistant_blocks=[],
        tool_calls=[],
        todos=[],
        source_path=source_path,
        stats=stats,
        adapter="generic",
    )


def _parse_uncached(jsonl: Path) -> ParsedTranscript:
    resolved = jsonl.expanduser().resolve()
    objects, lines_read = _read_objects(resolved)
    try:
        return _parse_cursor_objects(objects, lines_read=lines_read, source_path=resolved)
    except TranscriptSchemaError:
        return _parse_generic_objects(objects, lines_read=lines_read, source_path=resolved)


def parse_transcript(jsonl: Path, *, use_cache: bool = True) -> ParsedTranscript:
    """Parse jsonl once; cached by path + mtime."""
    resolved = jsonl.expanduser().resolve()
    key = str(resolved)
    try:
        mtime = resolved.stat().st_mtime
    except OSError as exc:
        raise TranscriptSchemaError(f"transcript not readable: {resolved}") from exc

    if use_cache and key in _PARSE_CACHE:
        cached_mtime, cached = _PARSE_CACHE[key]
        if cached_mtime == mtime:
            return cached

    parsed = _parse_uncached(resolved)
    _PARSE_CACHE[key] = (mtime, parsed)
    return parsed
