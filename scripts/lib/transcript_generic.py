"""Generic role/content jsonl adapter (exports, Claude Code, manual dumps)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from lib.transcript_cursor import ParseStats, TranscriptSchemaError, is_redacted_or_noise

WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def _text_from_obj(obj: dict) -> str | None:
    role = (obj.get("role") or obj.get("type") or "").lower()
    if role not in ("user", "human"):
        return None

    content = obj.get("content")
    if isinstance(content, str):
        return _normalize(content)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append(str(block["text"]))
            elif block.get("text"):
                parts.append(str(block["text"]))
        if parts:
            return _normalize(" ".join(parts))

    for key in ("message", "text", "body", "prompt"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return _normalize(val)

    return None


def extract_raw_user_texts(jsonl: Path) -> tuple[list[str], ParseStats]:
    if not jsonl.is_file():
        raise TranscriptSchemaError(f"transcript not found: {jsonl}")

    texts: list[str] = []
    stats = ParseStats()

    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        stats.lines_read += 1
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        stats.json_lines += 1
        raw = _text_from_obj(obj)
        if raw is None:
            continue
        stats.user_rows += 1
        stats.text_blocks += 1
        if is_redacted_or_noise(raw):
            continue
        texts.append(raw)

    if stats.json_lines == 0:
        raise TranscriptSchemaError(f"no JSON lines (not generic format?): {jsonl}")
    if stats.user_rows == 0:
        raise TranscriptSchemaError(f"no user/human rows: {jsonl}")
    if not texts:
        raise TranscriptSchemaError(f"only empty/noise user rows: {jsonl}")

    return texts, stats
