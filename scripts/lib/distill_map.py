"""Map-reduce distill — agent map per window, script reduce into staging."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.defaults import MAP_REDUCE_THRESHOLD, MAP_REDUCE_WINDOW_SIZE
from lib.message_importance import mechanical_bullets
from lib.secrets_guard import is_terminal_noise, sanitize_message
from lib.timestamps import now_iso, staging_date_slug
from lib.token_budget import window_messages
from lib.transcript import TranscriptSchemaError, extract_raw_user_texts
from lib.transcript_cursor import safe_path_component


def _snippet(msg: str, *, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", msg.strip())
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def windows_from_messages(messages: list[str]) -> list[dict[str, Any]]:
    chunks = window_messages(messages, window_size=MAP_REDUCE_WINDOW_SIZE)
    out: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, start=1):
        out.append(
            {
                "window": i,
                "messages": len(chunk),
                "samples": [_snippet(m) for m in chunk[:5]],
                "mechanical_bullets": mechanical_bullets(chunk, max_items=3),
            }
        )
    return out


def all_user_messages(extract: dict) -> list[str]:
    source = extract.get("source_path")
    if source:
        try:
            raw, _, _ = extract_raw_user_texts(Path(str(source)).expanduser())
            out: list[str] = []
            for text in raw:
                clean, _n = sanitize_message(text)
                if clean is None or is_terminal_noise(clean):
                    continue
                out.append(clean)
            if out:
                return out
        except TranscriptSchemaError:
            pass
    return list(extract.get("user_messages") or [])


def build_map_staging_markdown(extract: dict) -> str:
    slug = extract.get("workspace_slug", "unknown")
    uid = extract.get("uuid", "?")
    today = now_iso()
    messages = all_user_messages(extract)

    windows = windows_from_messages(messages) if messages else []
    if not windows and extract.get("window_summaries"):
        for win in extract["window_summaries"]:
            if isinstance(win, dict):
                windows.append(
                    {
                        "window": win.get("window", 0),
                        "messages": win.get("messages", 0),
                        "samples": [],
                        "mechanical_bullets": win.get("bullets") or [],
                    }
                )

    lines = [
        f"# Map staging — {slug}",
        f"_Generated: {today} · uuid: {uid}_",
        "",
        "> **Map phase:** fill `## Map (agent fills)` under each window (2–3 bullets).",
        "> Preserve chat language. Then: `python3 scripts/distill-map.py <uuid> --reduce`",
        "",
    ]
    for win in windows:
        wn = win.get("window", "?")
        lines.extend(
            [
                f"## Window {wn} ({win.get('messages', 0)} user msgs)",
                "",
                "### Samples",
                "",
            ]
        )
        samples = win.get("samples") or []
        if samples:
            for snip in samples:
                lines.append(f"- {snip}")
        else:
            for bullet in win.get("mechanical_bullets") or []:
                lines.append(f"- (mechanical) {bullet}")
        lines.extend(
            [
                "",
                "## Map (agent fills)",
                "",
                "- ",
                "",
            ]
        )
    return "\n".join(lines)


def parse_agent_map_bullets(map_md: str) -> dict[int, list[str]]:
    """Parse filled Map sections per window number."""
    current: int | None = None
    in_map = False
    by_window: dict[int, list[str]] = {}
    for line in map_md.splitlines():
        win = re.match(r"^## Window (\d+)", line)
        if win:
            current = int(win.group(1))
            in_map = False
            by_window.setdefault(current, [])
            continue
        if line.strip() == "## Map (agent fills)":
            in_map = True
            continue
        if line.startswith("## ") and in_map:
            in_map = False
            continue
        if in_map and current is not None and line.strip().startswith("- "):
            bullet = line.strip()[2:].strip()
            if bullet:
                by_window[current].append(bullet)
    return {k: v for k, v in by_window.items() if v}


def build_reduce_staging_markdown(
    extract: dict,
    agent_maps: dict[int, list[str]],
) -> str:
    slug = extract.get("workspace_slug", "unknown")
    uid = extract.get("uuid", "?")
    today = now_iso()
    lines = [
        f"# Reduce staging — {slug}",
        f"_Generated: {today} · uuid: {uid}_",
        "",
        "> Merged map bullets for semantic-merge (Decisions / Open threads).",
        "",
        "## Reduced map summaries",
        "",
    ]
    for wn in sorted(agent_maps):
        for bullet in agent_maps[wn]:
            lines.append(f"- [w{wn}] {bullet}")
    mech = extract.get("window_summaries") or []
    if mech:
        lines.extend(["", "## Mechanical fallback (reference)", ""])
        for win in mech:
            if not isinstance(win, dict):
                continue
            for bullet in win.get("bullets") or []:
                lines.append(f"- [w{win.get('window', '?')}] {bullet}")
    lines.append("")
    return "\n".join(lines)


def map_staging_path(memory_home: Path, extract: dict) -> Path:
    slug = safe_path_component(extract.get("workspace_slug", "unknown"))
    uid = safe_path_component(str(extract.get("uuid", "chat"))[:8])
    today = staging_date_slug(now_iso())
    return memory_home / "chats" / "map-staging" / f"{slug}-{today}-{uid}.md"


def reduce_staging_path(memory_home: Path, extract: dict) -> Path:
    slug = safe_path_component(extract.get("workspace_slug", "unknown"))
    uid = safe_path_component(str(extract.get("uuid", "chat"))[:8])
    today = staging_date_slug(now_iso())
    return memory_home / "chats" / "reduce-staging" / f"{slug}-{today}-{uid}.md"


def write_map_staging(memory_home: Path, extract: dict) -> Path | None:
    total = int(extract.get("user_message_count") or 0)
    windows = extract.get("window_summaries") or []
    if not windows and total < MAP_REDUCE_THRESHOLD:
        return None
    path = map_staging_path(memory_home, extract)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_map_staging_markdown(extract), encoding="utf-8")
    return path


def run_reduce(
    memory_home: Path,
    extract: dict,
    map_staging: Path,
) -> Path:
    agent_maps = parse_agent_map_bullets(map_staging.read_text(encoding="utf-8"))
    if not agent_maps:
        raise ValueError(
            "no agent map bullets found — fill ## Map (agent fills) sections first"
        )
    out = reduce_staging_path(memory_home, extract)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build_reduce_staging_markdown(extract, agent_maps),
        encoding="utf-8",
    )
    return out
