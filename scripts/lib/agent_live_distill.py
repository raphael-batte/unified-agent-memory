"""Agent-written live distill (*-live.md) on preCompact boundary."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.project_merge import _bullets
from lib.transcript_cursor import safe_path_component

_LIVE_SUFFIX = "-live.md"
_SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)


def live_staging_basename(slug: str, date_slug: str, chat_id: str) -> str:
    safe_id = safe_path_component(chat_id, fallback="chat")[:8]
    safe_slug = safe_path_component(slug, fallback="unknown")
    return f"{safe_slug}-{date_slug}-{safe_id}{_LIVE_SUFFIX}"


def live_staging_path(
    memory_home: Path,
    *,
    slug: str,
    date_slug: str,
    chat_id: str,
) -> Path:
    return memory_home / "chats" / "merge-staging" / live_staging_basename(
        slug, date_slug, chat_id
    )


def find_agent_live_file(
    memory_home: Path,
    *,
    slug: str,
    chat_id: str,
) -> Path | None:
    staging = memory_home / "chats" / "merge-staging"
    if not staging.is_dir():
        return None
    safe_slug = safe_path_component(slug, fallback="unknown")
    needle = f"-{safe_path_component(chat_id, fallback='chat')[:8]}{_LIVE_SUFFIX}"
    matches = sorted(
        (p for p in staging.glob(f"{safe_slug}-*{needle}") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _sections_from_markdown(text: str) -> dict[str, str]:
    parts = _SECTION_HEADING.split(text)
    if len(parts) < 2:
        return {}
    sections: dict[str, str] = {}
    i = 1
    while i + 1 < len(parts):
        title = parts[i].strip().lower()
        body = parts[i + 1].strip()
        sections[title] = body
        i += 2
    return sections


def parse_agent_live_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = _sections_from_markdown(text)
    summary_key = next((k for k in sections if k.startswith("summary")), None)
    next_key = next(
        (k for k in sections if "next step" in k or k.startswith("next step")),
        None,
    )
    summary_bullets = _bullets(sections.get(summary_key or "", ""))
    next_bullets = _bullets(sections.get(next_key or "", ""))
    next_step = next_bullets[0] if next_bullets else None
    summary = summary_bullets[0] if summary_bullets else None
    return {
        "path": str(path),
        "summary": summary,
        "summary_bullets": summary_bullets[:5],
        "next_step": next_step,
    }


def enrich_extract_with_agent_live(
    extract: dict,
    *,
    memory_home: Path,
    chat_id: str,
) -> dict:
    slug = str(
        extract.get("workspace_slug")
        or safe_path_component(extract.get("workspace", ""), fallback="unknown")
    )
    live_path = find_agent_live_file(memory_home, slug=slug, chat_id=chat_id)
    if live_path is None:
        return extract
    parsed = parse_agent_live_file(live_path)
    if not parsed.get("summary") and not parsed.get("next_step"):
        return extract
    out = dict(extract)
    out["agent_live"] = parsed
    if parsed.get("summary"):
        out["final_summary"] = parsed["summary"]
    return out


def build_precompact_user_message(
    memory_home: Path,
    distill: dict[str, Any],
    *,
    framework_root: Path,
) -> str:
    base = "[agent-memory] Context compacting — write agent live distill before context is lost."
    if distill.get("status") != "distilled":
        return base + " Review merge-staging and latest distills."

    slug = str(distill.get("slug") or "unknown")
    chat_id = str(distill.get("chat_id") or "unknown")
    from lib.timestamps import now_iso, staging_date_slug

    raw_date = str(distill.get("distilled_at") or now_iso())[:10]
    date_slug = staging_date_slug(raw_date)
    live_path = live_staging_path(
        memory_home, slug=slug, date_slug=date_slug, chat_id=chat_id
    )
    staging = str(distill.get("staging_path") or "")
    prompt_rel = "templates/chats/live-distill-prompt.md"
    prompt_path = framework_root / prompt_rel
    lines = [
        base,
        f"Follow `{prompt_rel}` (framework: {prompt_path}).",
        f"Write: `{live_path}`",
    ]
    if staging:
        lines.append(f"Mechanical staging: `{staging}`")
    lines.append(
        "Sections required: ## Summary (1–3 bullets), optional ## Next step candidate."
    )
    return " ".join(lines)
