"""Session-start pointer feedback — disk pointer + session adherence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.chats_manifest import load_manifest, processed_by_id
from lib.defaults import DOMAIN_STOPWORDS
from lib.forward_pointer import NO_POINTER_MARKER, STALE_POINTER_PREFIX
from lib.pointer_metrics import log_pointer_feedback
from lib.pointer_provenance import is_curated_next_step, strip_curated_marker
from lib.project_merge import _bullets, _parse_sections
from lib.transcript_cursor import safe_path_component
from lib.transcript_parse import parse_transcript

_PLACEHOLDER_RE = re.compile(r"^\[\?\]")
_TOKEN_RE = re.compile(r"[\w\u0400-\u04ff]+", re.UNICODE)
_GENERIC_START = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "continue",
        "thanks",
        "ok",
        "okay",
        "\u043f\u0440\u0438\u0432\u0435\u0442",
        "\u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0439",
        "\u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u043c",
        "\u0434\u0430\u0432\u0430\u0439",
        "\u0441\u043f\u0430\u0441\u0438\u0431\u043e",
        "\u043e\u043a",
        "\u043e\u043a\u0435\u0439",
    }
)


def _project_path(memory_home: Path, slug: str) -> Path:
    safe = safe_path_component(slug, fallback="project")
    return memory_home / "chats" / "projects" / f"{safe}.md"


def _pointer_from_project(project_path: Path) -> tuple[str | None, bool]:
    if not project_path.is_file():
        return None, False
    _preamble, sections = _parse_sections(
        project_path.read_text(encoding="utf-8", errors="replace")
    )
    for bullet in _bullets(sections.get("Next step", "")):
        curated = is_curated_next_step(bullet)
        text = strip_curated_marker(bullet)
        if NO_POINTER_MARKER in bullet or _PLACEHOLDER_RE.match(bullet.strip()):
            return None, curated
        if text and not bullet.strip().startswith(STALE_POINTER_PREFIX):
            return text, curated
    return None, False


def _latest_pointer_source(memory_home: Path, slug: str) -> str | None:
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    rel = f"projects/{safe_path_component(slug, fallback='project')}.md"
    best: dict[str, Any] | None = None
    for entry in processed_by_id(manifest).values():
        targets = entry.get("distilled_to") or []
        if rel not in targets:
            continue
        if best is None or str(entry.get("distilled_at") or "") >= str(
            best.get("distilled_at") or ""
        ):
            best = entry
    if best:
        src = best.get("pointer_source")
        return str(src) if src else None
    return None


def _manifest_entry_for_slug(memory_home: Path, slug: str) -> dict[str, Any] | None:
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    rel = f"projects/{safe_path_component(slug, fallback='project')}.md"
    best: dict[str, Any] | None = None
    for entry in processed_by_id(manifest).values():
        targets = entry.get("distilled_to") or []
        if rel not in targets:
            continue
        if best is None or str(entry.get("distilled_at") or "") >= str(
            best.get("distilled_at") or ""
        ):
            best = entry
    return best


def _significant_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if len(tok) > 2 and tok not in DOMAIN_STOPWORDS
    }


def token_overlap_ratio(pointer: str, texts: list[str]) -> float:
    ptr_tokens = _significant_tokens(pointer)
    if not ptr_tokens:
        return 0.0
    session_tokens: set[str] = set()
    for text in texts:
        session_tokens |= _significant_tokens(text)
    if not session_tokens:
        return 0.0
    return len(ptr_tokens & session_tokens) / len(ptr_tokens)


def _session_tail_messages(
    parsed,
    manifest_entry: dict[str, Any] | None,
    *,
    max_msgs: int = 5,
) -> list[str]:
    wm = int(manifest_entry.get("watermark_user_count") or 0) if manifest_entry else 0
    msgs = parsed.user_messages
    if wm < len(msgs):
        tail = msgs[wm : wm + max_msgs]
    elif msgs:
        tail = msgs[-max_msgs:]
    else:
        tail = []
    return [m.text for m in tail if m.text.strip()]


def classify_session_adherence(
    pointer: str,
    session_user_msgs: list[str],
    open_todo: str | None,
) -> tuple[str, float]:
    msgs = [m.strip() for m in session_user_msgs if m and m.strip()]
    if not msgs:
        return "unmeasured", 0.0

    first_norm = msgs[0].lower().strip()
    first_tokens = _significant_tokens(first_norm)
    generic_start = (
        len(first_norm) < 10
        or first_tokens <= _GENERIC_START
        or first_norm in _GENERIC_START
    )

    per_msg = [token_overlap_ratio(pointer, [m]) for m in msgs[:5]]
    max_msg = max(per_msg) if per_msg else 0.0
    todo_score = token_overlap_ratio(pointer, [open_todo]) if open_todo else 0.0
    combined = max(max_msg, todo_score)

    if combined >= 0.35:
        return "followed", combined
    if combined >= 0.12:
        return "partial", combined
    if generic_start:
        return "resumed_blind", combined
    return "ignored", combined


def classify_pointer_outcome(
    pointer: str | None,
    *,
    session_outcome: str | None,
) -> str:
    if not pointer:
        return "miss"
    if session_outcome:
        return session_outcome
    return "unmeasured"


def _chat_id_from_payload(payload: dict[str, Any]) -> str | None:
    transcript = payload.get("transcript_path")
    if isinstance(transcript, str) and transcript.strip():
        stem = Path(transcript).stem
        if stem:
            return stem
    conversation_id = payload.get("conversation_id")
    if isinstance(conversation_id, str) and conversation_id.strip():
        return conversation_id.strip()
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    return None


def _resolve_transcript_jsonl(
    payload: dict[str, Any],
    *,
    memory_home: Path,
    projects_root: Path,
) -> Path | None:
    transcript = payload.get("transcript_path")
    if isinstance(transcript, str) and transcript.strip():
        path = Path(transcript).expanduser()
        if path.is_file():
            return path.resolve()
    chat_id = _chat_id_from_payload(payload)
    if not chat_id:
        return None
    from lib.transcript import find_transcript

    return find_transcript(chat_id, projects_root, memory_home=memory_home)


def _slug_from_jsonl(jsonl: Path, projects_root: Path) -> str | None:
    from lib.transcript import workspace_slug, workspace_from_path

    ws = workspace_from_path(jsonl, projects_root)
    if not ws:
        return None
    return workspace_slug(ws)


def log_session_start_pointer_feedback(
    memory_home: Path,
    workspace_slugs: set[str] | list[str],
    *,
    payload: dict[str, Any] | None = None,
    projects_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Log pointer_feedback per open workspace slug."""
    active_slug: str | None = None
    active_jsonl: Path | None = None
    active_parsed = None
    active_manifest_entry: dict[str, Any] | None = None

    if payload is not None and projects_root is not None:
        active_jsonl = _resolve_transcript_jsonl(
            payload, memory_home=memory_home, projects_root=projects_root
        )
        if active_jsonl is not None:
            active_slug = _slug_from_jsonl(active_jsonl, projects_root)
            active_parsed = parse_transcript(active_jsonl)
            if active_slug:
                active_manifest_entry = _manifest_entry_for_slug(memory_home, active_slug)

    logged: list[dict[str, Any]] = []
    for raw_slug in sorted(set(workspace_slugs)):
        slug = str(raw_slug).strip()
        if not slug:
            continue
        project_path = _project_path(memory_home, slug)
        if not project_path.is_file():
            row = {
                "outcome": "skip",
                "workspace_slug": slug,
                "disk_hit": False,
                "session_outcome": None,
                "overlap_score": None,
                "curated": False,
                "pointer_source": _latest_pointer_source(memory_home, slug),
                "pointer_preview": None,
            }
            log_pointer_feedback(memory_home, row)
            logged.append(row)
            continue

        pointer, curated = _pointer_from_project(project_path)
        session_outcome: str | None = None
        overlap_score: float | None = None

        slug_norm = safe_path_component(slug, fallback="").lower()
        active_norm = (
            safe_path_component(active_slug or "", fallback="").lower()
            if active_slug
            else ""
        )
        if pointer and slug_norm == active_norm and active_parsed is not None:
            tail_msgs = _session_tail_messages(
                active_parsed,
                active_manifest_entry,
            )
            open_todo = None
            todos = active_parsed.open_todos()
            if todos:
                open_todo = todos[0].content
            session_outcome, overlap_score = classify_session_adherence(
                pointer, tail_msgs, open_todo
            )

        outcome = classify_pointer_outcome(
            pointer, session_outcome=session_outcome
        )
        row = {
            "outcome": outcome,
            "workspace_slug": slug,
            "disk_hit": bool(pointer),
            "session_outcome": session_outcome,
            "overlap_score": round(overlap_score, 3) if overlap_score is not None else None,
            "curated": curated,
            "pointer_source": _latest_pointer_source(memory_home, slug),
            "pointer_preview": (pointer or "")[:120] or None,
        }
        log_pointer_feedback(memory_home, row)
        logged.append(row)
    return logged
