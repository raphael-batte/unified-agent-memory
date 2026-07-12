"""Auto-draft ## Open threads from distill extract (cron/boundary pipeline)."""

from __future__ import annotations

import re
from pathlib import Path

from lib.defaults import DECISION_JUNK_MIN_LEN
from lib.markdown_sections import bullets as _bullets
from lib.markdown_sections import parse_sections as _parse_sections
from lib.novelty import is_decision_junk
from lib.project_merge import (
    MAX_OPEN_THREADS,
    TIER_AUTO,
    _format_bullets,
    _join_sections,
    _today,
    upsert_open_thread_tiered,
)
from lib.secrets_guard import scan_file
from lib.transcript_cursor import safe_path_component

WORK_PATH_RE = re.compile(
    r"(?:~/" + "Work/|(?:^|\s)work/)([a-zA-Z0-9][a-zA-Z0-9_\-/]*)",
    re.I | re.M,
)
LABEL_SLUG_RE = re.compile(r"[^\w\-]+", re.UNICODE)
OPEN_THREAD_DRAFT_MAX_TEXT = 200
OPEN_THREAD_DRAFT_MAX_LABEL = 24


def is_open_thread_draft_junk(text: str) -> bool:
    body = text.strip()
    if len(body) < DECISION_JUNK_MIN_LEN:
        return True
    return is_decision_junk(body)


def is_open_thread_label_junk(label: str) -> bool:
    body = label.strip()
    if len(body) < 2:
        return True
    return is_decision_junk(body)


def _slugify_label(text: str) -> str:
    slug = LABEL_SLUG_RE.sub("-", text.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:OPEN_THREAD_DRAFT_MAX_LABEL]


def _label_from_work_path(message: str) -> str | None:
    for match in WORK_PATH_RE.finditer(message):
        raw = match.group(1).strip("/\\")
        parts = [
            p
            for p in re.split(r"[/\\]", raw)
            if p and p.lower() not in {"work", "www", "src", "lib"}
        ]
        if not parts:
            continue
        if len(parts) >= 2:
            label = f"{parts[0]}-{parts[1]}"
        else:
            label = parts[0]
        label = _slugify_label(label)
        if label and not is_open_thread_label_junk(label):
            return label
    return None


def infer_direction_label(extract: dict, segment: dict | None) -> str | None:
    """Path in messages first, then tail segment preview, then workspace slug."""
    for msg in reversed(extract.get("user_messages") or []):
        if not isinstance(msg, str):
            continue
        from_path = _label_from_work_path(msg)
        if from_path:
            return from_path

    preview = ""
    if segment:
        preview = str(segment.get("preview") or "")
    if not preview:
        preview = str(extract.get("first_query") or "")
    slug = _slugify_label(preview)
    if slug and not is_open_thread_label_junk(slug):
        return slug

    fallback = safe_path_component(
        str(extract.get("workspace_slug") or ""),
        fallback="",
    )
    fallback = _slugify_label(fallback.replace("_", "-"))
    return fallback or None


def draft_text_from_extract(extract: dict, segment: dict | None) -> str:
    if segment and segment.get("preview"):
        text = str(segment["preview"]).strip()
        if text and not is_open_thread_draft_junk(text):
            return text[:OPEN_THREAD_DRAFT_MAX_TEXT]

    for msg in reversed(extract.get("user_messages") or []):
        if not isinstance(msg, str):
            continue
        clean = msg.strip()
        if clean and not is_open_thread_draft_junk(clean):
            return clean[:OPEN_THREAD_DRAFT_MAX_TEXT]

    text = str(extract.get("first_query") or "").strip()
    return text[:OPEN_THREAD_DRAFT_MAX_TEXT]


def usable_topic_segment(extract: dict) -> dict | None:
    """Last segment whose preview is not junk (skip trailing system/meta tails)."""
    segments = extract.get("topic_segments") or []
    for segment in reversed(segments):
        preview = str(segment.get("preview") or "").strip()
        if preview and not is_open_thread_draft_junk(preview):
            return segment
    return segments[-1] if segments else None


def tail_topic_segment(extract: dict) -> dict | None:
    return usable_topic_segment(extract)


def draft_open_threads_after_apply(
    project_path: Path,
    extract: dict,
    *,
    today: str | None = None,
) -> dict:
    """
    Write one ``[auto]`` Open threads bullet from the tail topic segment.

    Does not run inside ``apply_extract_to_project`` (curated-only contract).
    """
    result: dict = {
        "drafted": False,
        "needs_curation": False,
        "label": None,
        "skip_reason": "",
    }
    if not project_path.is_file():
        result["skip_reason"] = "no_project_file"
        return result

    segment = tail_topic_segment(extract)
    label = infer_direction_label(extract, segment)
    text = draft_text_from_extract(extract, segment)
    updated = str(extract.get("date") or today or _today())[:10]

    if not label:
        result["skip_reason"] = "no_label"
        return result
    if is_open_thread_draft_junk(text):
        result["skip_reason"] = "junk_text"
        return result

    raw = project_path.read_text(encoding="utf-8", errors="replace")
    preamble, sections = _parse_sections(raw)
    existing = _bullets(sections.get("Open threads", ""))
    updated_bullets, changed, skip_reason = upsert_open_thread_tiered(
        existing,
        label,
        text,
        updated=updated,
        tier=TIER_AUTO,
        cap=MAX_OPEN_THREADS,
    )
    if not changed:
        result["skip_reason"] = skip_reason or "unchanged"
        return result

    sections["Open threads"] = _format_bullets(updated_bullets)
    merged = _join_sections(preamble, sections)

    tmp = project_path.with_suffix(".md.tmpdraft")
    tmp.write_text(merged, encoding="utf-8")
    try:
        hits = scan_file(tmp)
        if hits:
            result["skip_reason"] = "secrets_detected"
            return result
    finally:
        tmp.unlink(missing_ok=True)

    project_path.write_text(merged, encoding="utf-8")
    result["drafted"] = True
    result["needs_curation"] = True
    result["label"] = label
    return result
