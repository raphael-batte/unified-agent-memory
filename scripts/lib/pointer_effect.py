"""Measure whether the forward pointer (## Open threads) is actually used.

The old ``pointer_feedback`` scored a session at ``sessionStart``, before the
user had typed anything, so every row came out ``unmeasured``. It also scored
all threads glued into one string and marked any thread as curated.

This module splits the job in two:

1. **Shown** — what the agent was given. Claude records the threads of the
   first prompt-submit injection per session. Cursor has no events, so the hub
   keeps snapshots of its threads; a chat is matched to the last snapshot taken
   before it started. Claude falls back to the same snapshot when it has no
   injection on record.
2. **Outcome** — scored later, once per chat, from the first user messages:
   per-thread token overlap, a generic-start flag ("continue"), and
   memory-miss cues ("I already told you").

Outcomes land in the metrics log as ``pointer_outcome`` rows; ``memory-health``
aggregates them.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from lib.defaults import GENERIC_MESSAGE_START
from lib.distill_metrics import append_metric
from lib.hub_lock import write_json_atomic
from lib.open_threads import OpenThread, collect_open_threads
from lib.pointer_feedback import token_overlap_ratio

#: Threads the agent sees — same cap as the Claude injection block.
SHOWN_MAX_THREADS = 5
#: Score on the opening of the session, where a pointer can steer it.
OPENING_MESSAGES = 5
#: Memory-miss cues are looked for a little further in.
MISS_SCAN_MESSAGES = 10
#: Enough user turns to score without waiting for the session to end.
MIN_MESSAGES_LIVE = 3
FOLLOWED_AT = 0.35
PARTIAL_AT = 0.12
#: A chat quiet for this long is scored with whatever it has.
IDLE_FINAL = timedelta(hours=2)
#: Chats older than this are not scored by the cron backlog pass.
BACKLOG_DAYS = 3
MAX_SNAPSHOTS = 60
STATE_RETENTION_DAYS = 45
_TEXT_CAP = 200
_AUTO_PREFIX = "[auto]"

_STATE_FILE = "pointer-effect.json"


# ── state ──────────────────────────────────────────────────────────────────


def _state_path(memory_home: Path) -> Path:
    return memory_home / ".state" / _STATE_FILE


def _load_state(memory_home: Path) -> dict[str, Any]:
    path = _state_path(memory_home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("snapshots", [])
    data.setdefault("shown", {})
    data.setdefault("evaluated", {})
    return data


def _save_state(memory_home: Path, data: dict[str, Any]) -> None:
    cutoff = (datetime.now() - timedelta(days=STATE_RETENTION_DAYS)).isoformat()
    data["snapshots"] = data["snapshots"][-MAX_SNAPSHOTS:]
    for key in ("shown", "evaluated"):
        data[key] = {
            k: v
            for k, v in data[key].items()
            if str((v or {}).get("ts") or "") >= cutoff
        }
    write_json_atomic(_state_path(memory_home), data)


# ── shown ──────────────────────────────────────────────────────────────────


def thread_record(thread: OpenThread) -> dict[str, Any]:
    text = thread.text.strip()
    return {
        "slug": thread.slug,
        "label": thread.label,
        "text": text[:_TEXT_CAP],
        "curated": not text.startswith(_AUTO_PREFIX),
        "age_days": thread.age_days,
    }


def _shown_from(records: list[dict[str, Any]], priority_slug: str | None) -> list[dict]:
    """Same ordering the injection uses: workspace first, then newest."""
    if priority_slug:
        first = [r for r in records if r.get("slug") == priority_slug]
        rest = [r for r in records if r.get("slug") != priority_slug]
        records = first + rest
    return records[:SHOWN_MAX_THREADS]


def record_snapshot(memory_home: Path, *, now: datetime | None = None) -> bool:
    """Store the hub's current threads when they differ from the last snapshot."""
    now = now or datetime.now()
    threads = [thread_record(t) for t in collect_open_threads(memory_home, now=now)]
    data = _load_state(memory_home)
    last = data["snapshots"][-1]["threads"] if data["snapshots"] else None
    if last == threads:
        return False
    data["snapshots"].append({"ts": now.isoformat(timespec="seconds"), "threads": threads})
    _save_state(memory_home, data)
    return True


def record_shown(
    memory_home: Path,
    session_id: str,
    threads: list[OpenThread],
    *,
    env: str,
) -> bool:
    """Remember the first injection of a session; later ones may hold threads
    this very session wrote (preCompact distills), so they are ignored."""
    if not session_id or not threads:
        return False
    data = _load_state(memory_home)
    if session_id in data["shown"]:
        return False
    data["shown"][session_id] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "env": env,
        "threads": [thread_record(t) for t in threads[:SHOWN_MAX_THREADS]],
    }
    _save_state(memory_home, data)
    return True


def _snapshot_before(
    data: dict[str, Any], started: datetime
) -> list[dict[str, Any]] | None:
    stamp = started.isoformat(timespec="seconds")
    best = None
    for snap in data["snapshots"]:
        if str(snap.get("ts") or "") <= stamp:
            best = snap
    return best["threads"] if best else None


# ── scoring ────────────────────────────────────────────────────────────────


def _miss_pattern(cues: list[str]) -> re.Pattern[str] | None:
    parts = [re.escape(c) for c in cues if c]
    if not parts:
        return None
    return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})(?!\w)", re.I)


def is_generic_start(text: str) -> bool:
    norm = re.sub(r"[^\w\s]", " ", text.lower()).split()
    if not norm:
        return True
    return len(" ".join(norm)) < 10 or all(tok in GENERIC_MESSAGE_START for tok in norm)


def score_session(
    shown: list[dict[str, Any]],
    user_messages: list[str],
    *,
    miss_cues: list[str] | None = None,
) -> dict[str, Any]:
    msgs = [m.strip() for m in user_messages if m and m.strip()]
    opening = msgs[:OPENING_MESSAGES]
    generic = bool(msgs) and is_generic_start(msgs[0])
    # After a bare "continue" the real direction shows up in the next turns.
    scored_msgs = opening[1:] if generic and len(opening) > 1 else opening

    best: tuple[float, dict[str, Any]] | None = None
    best_curated = 0.0
    best_auto = 0.0
    for thread in shown:
        probe = f"{thread.get('label') or ''} {thread.get('text') or ''}"
        probe = probe.replace(_AUTO_PREFIX, " ")
        score = token_overlap_ratio(probe, scored_msgs) if scored_msgs else 0.0
        if thread.get("curated"):
            best_curated = max(best_curated, score)
        else:
            best_auto = max(best_auto, score)
        if best is None or score > best[0]:
            best = (score, thread)

    top = best[0] if best else 0.0
    if not shown:
        outcome = "nothing_shown"
    elif not msgs:
        outcome = "unmeasured"
    elif top >= FOLLOWED_AT:
        outcome = "followed"
    elif top >= PARTIAL_AT:
        outcome = "partial"
    else:
        outcome = "new_topic"

    pattern = _miss_pattern(miss_cues or [])
    miss = bool(pattern) and any(pattern.search(m) for m in msgs[:MISS_SCAN_MESSAGES])

    return {
        "outcome": outcome,
        "score": round(top, 3),
        "generic_start": generic,
        "memory_miss": miss,
        "threads_shown": len(shown),
        "curated_shown": sum(1 for t in shown if t.get("curated")),
        "best_slug": best[1].get("slug") if best and top > 0 else None,
        "best_curated": bool(best[1].get("curated")) if best and top > 0 else None,
        "curated_score": round(best_curated, 3),
        "auto_score": round(best_auto, 3),
        "messages": len(msgs),
    }


# ── evaluation ─────────────────────────────────────────────────────────────


def _started_at(parsed, jsonl: Path) -> datetime:
    for msg in parsed.user_messages:
        if msg.timestamp:
            try:
                ts = datetime.fromisoformat(str(msg.timestamp).replace("Z", "+00:00"))
                return ts.astimezone().replace(tzinfo=None)
            except ValueError:
                break
    st = jsonl.stat()
    return datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_mtime))


def evaluate_chat(
    memory_home: Path,
    jsonl: Path,
    *,
    env: str,
    final: bool = False,
    workspace_slug: str | None = None,
) -> dict[str, Any] | None:
    """Score one chat once. Returns the logged row, or None when not (yet) due."""
    from lib.lang_cues import load_lang_cues
    from lib.transcript_parse import parse_transcript

    chat_id = jsonl.stem
    data = _load_state(memory_home)
    if chat_id in data["evaluated"]:
        return None
    try:
        parsed = parse_transcript(jsonl)
    except Exception:
        return None
    msgs = parsed.user_texts()
    if not msgs or (not final and len(msgs) < MIN_MESSAGES_LIVE):
        return None

    shown_row = data["shown"].get(chat_id)
    if shown_row:
        shown = shown_row.get("threads") or []
        source = "injected"
    else:
        snap = _snapshot_before(data, _started_at(parsed, jsonl))
        if snap is None:
            # No record of what the agent saw: do not guess.
            data["evaluated"][chat_id] = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "outcome": "no_snapshot",
            }
            _save_state(memory_home, data)
            return None
        shown = _shown_from(snap, workspace_slug)
        source = "snapshot"

    cues = load_lang_cues(memory_home=memory_home).get("memory_miss_cues") or []
    row = score_session(shown, msgs, miss_cues=cues)
    row.update(
        {
            "event": "pointer_outcome",
            "env": env,
            "chat_id": chat_id,
            "shown_source": source,
            "workspace_slug": workspace_slug,
        }
    )
    append_metric(memory_home, row)
    data["evaluated"][chat_id] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "outcome": row["outcome"],
    }
    _save_state(memory_home, data)
    return row


def evaluate_backlog(
    memory_home: Path,
    *,
    now: datetime | None = None,
    days: int = BACKLOG_DAYS,
) -> dict[str, int]:
    """Cron pass: score recent chats from every environment that are due."""
    from lib.chats_manifest import load_manifest
    from lib.transcript import find_transcript, workspace_slug

    now = now or datetime.now()
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    data = _load_state(memory_home)
    since = (now - timedelta(days=days)).date().isoformat()
    stats = {"scored": 0, "waiting": 0, "no_snapshot": 0, "skipped": 0}
    for entry in manifest.get("processed") or []:
        chat_id = str(entry.get("id") or "")
        if not chat_id or chat_id in data["evaluated"]:
            continue
        if str(entry.get("date") or "") < since:
            continue
        jsonl = find_transcript(chat_id, memory_home=memory_home)
        if jsonl is None:
            stats["skipped"] += 1
            continue
        idle = now - datetime.fromtimestamp(os.path.getmtime(jsonl))
        ws = entry.get("workspace")
        row = evaluate_chat(
            memory_home,
            jsonl,
            env=str(entry.get("env") or "cursor"),
            final=idle >= IDLE_FINAL,
            workspace_slug=workspace_slug(ws) if ws else None,
        )
        data = _load_state(memory_home)
        if row is not None:
            stats["scored"] += 1
        elif chat_id in data["evaluated"]:
            stats["no_snapshot"] += 1
        else:
            stats["waiting"] += 1
    return stats


# ── aggregation ────────────────────────────────────────────────────────────


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Latest outcome per chat → rates for status/health."""
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("event") == "pointer_outcome" and row.get("chat_id"):
            latest[str(row["chat_id"])] = row
    scored = [r for r in latest.values() if r.get("outcome") in ("followed", "partial", "new_topic")]
    n = len(scored)

    def rate(pred, pool=None) -> float | None:
        pool = scored if pool is None else pool
        return round(sum(1 for r in pool if pred(r)) / len(pool), 3) if pool else None

    with_curated = [r for r in scored if r.get("curated_shown")]
    with_auto = [r for r in scored if (r.get("threads_shown") or 0) > (r.get("curated_shown") or 0)]
    by_env = {}
    for env in sorted({str(r.get("env") or "?") for r in scored}):
        pool = [r for r in scored if str(r.get("env") or "?") == env]
        by_env[env] = {"n": len(pool), "followed_rate": rate(lambda r: r["outcome"] == "followed", pool)}
    blind = [r for r in scored if r.get("generic_start")]
    return {
        "sessions": n,
        "followed_rate": rate(lambda r: r["outcome"] == "followed"),
        "partial_rate": rate(lambda r: r["outcome"] == "partial"),
        "new_topic_rate": rate(lambda r: r["outcome"] == "new_topic"),
        "curated_followed_rate": rate(lambda r: (r.get("curated_score") or 0) >= FOLLOWED_AT, with_curated),
        "auto_followed_rate": rate(lambda r: (r.get("auto_score") or 0) >= FOLLOWED_AT, with_auto),
        "curated_sessions": len(with_curated),
        "auto_sessions": len(with_auto),
        "blind_resumes": len(blind),
        "blind_followed_rate": rate(lambda r: r["outcome"] == "followed", blind),
        "memory_miss_rate": rate(lambda r: bool(r.get("memory_miss"))),
        "by_env": by_env,
    }
