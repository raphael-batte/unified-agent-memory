"""Cursor boundary hooks — sessionStart catch-up distill, preCompact/sessionEnd distill."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.boundary_crash import report_exception  # noqa: E402
from lib.boundary_debounce import record_boundary_distill, should_skip_debounce  # noqa: E402
from lib.chats_manifest import load_manifest, processed_by_id  # noqa: E402
from lib.defaults import POINTER_LOW_CONFIDENCE  # noqa: E402
from lib.distill_metrics import append_metric  # noqa: E402
from lib.pointer_curation_queue import (  # noqa: E402
    enqueue as enqueue_pointer,
    needs_enqueue,
    session_start_user_message,
)
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.pending_chats import (  # noqa: E402
    list_chats_needing_distill,
    needs_distill,
    slugs_from_workspace_roots,
)
from lib.live_distill import run_live_distill, should_live_distill  # noqa: E402
from lib.pointer_feedback import log_session_start_pointer_feedback  # noqa: E402
from lib.transcript import TranscriptSchemaError, find_transcript  # noqa: E402

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"
BOUNDARY_EVENTS = frozenset({"preCompact", "sessionEnd"})
SESSION_START_CATCHUP_LIMIT = 5
SESSION_START_DAYS = 180


def chat_id_from_payload(payload: dict[str, Any]) -> str | None:
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


def resolve_transcript_jsonl(
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

    chat_id = chat_id_from_payload(payload)
    if not chat_id:
        return None
    return find_transcript(chat_id, projects_root, memory_home=memory_home)


def should_skip_boundary_distill(
    *,
    memory_home: Path,
    chat_id: str,
    jsonl: Path,
) -> str | None:
    """Return skip reason if distill not needed."""
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    if needs_distill(chat_id, jsonl, manifest):
        return None
    return "already_distilled"


_DISTILL_MODULES_CACHE: tuple[Any, Any] | None = None


def _load_distill_modules() -> tuple[Any, Any]:
    global _DISTILL_MODULES_CACHE
    if _DISTILL_MODULES_CACHE is not None:
        return _DISTILL_MODULES_CACHE
    extract_spec = importlib.util.spec_from_file_location(
        "distill_extract_mod", SCRIPT_DIR / "distill-extract.py"
    )
    merge_spec = importlib.util.spec_from_file_location(
        "distill_merge_mod", SCRIPT_DIR / "distill-merge.py"
    )
    if (
        extract_spec is None
        or extract_spec.loader is None
        or merge_spec is None
        or merge_spec.loader is None
    ):
        raise RuntimeError("distill modules unavailable")
    extract_mod = importlib.util.module_from_spec(extract_spec)
    merge_mod = importlib.util.module_from_spec(merge_spec)
    extract_spec.loader.exec_module(extract_mod)
    merge_spec.loader.exec_module(merge_mod)
    _DISTILL_MODULES_CACHE = (extract_mod, merge_mod)
    return _DISTILL_MODULES_CACHE


def _record_metric(memory_home: Path, row: dict[str, Any]) -> None:
    try:
        append_metric(memory_home, row)
    except OSError:
        pass


def distill_jsonl(
    jsonl: Path,
    *,
    memory_home: Path,
    projects_root: Path,
    strategy: str = "auto",
    apply: bool = True,
    bootstrap_decisions: bool = False,
    event: str | None = None,
) -> dict[str, Any]:
    chat_id = jsonl.stem
    extract_mod, merge_mod = _load_distill_modules()
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    manifest_entry = processed_by_id(manifest).get(chat_id)
    t0 = time.perf_counter()
    try:
        extract = extract_mod.build_extract(
            jsonl,
            projects_root=projects_root,
            strategy=strategy,
            memory_home=memory_home,
            manifest_entry=manifest_entry,
        )
    except TranscriptSchemaError as exc:
        out = {
            "status": "error",
            "reason": "transcript_schema",
            "detail": str(exc),
            "chat_id": chat_id,
        }
        _record_metric(
            memory_home,
            {
                "event": event or "distill",
                "status": "error",
                "chat_id": chat_id,
                "reason": "transcript_schema",
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            },
        )
        return out
    merge_result = merge_mod.run_merge(
        memory_home=memory_home,
        chat_id=chat_id,
        extract=extract,
        dry_run=False,
        apply=apply,
        force_apply=apply,
        bootstrap_decisions=bootstrap_decisions,
    )
    duration_ms = int((time.perf_counter() - t0) * 1000)
    apply_result = merge_result.get("apply_result") or {}
    _record_metric(
        memory_home,
        {
            "event": event or "distill",
            "status": "distilled",
            "chat_id": chat_id,
            "duration_ms": duration_ms,
            "user_message_count": extract.get("user_message_count"),
            "messages_used": len(extract.get("user_messages") or []),
            "strategy": extract.get("strategy"),
            "truncated": bool(extract.get("truncated")),
            "secrets_redacted": int(extract.get("secrets_redacted") or 0),
            "pointer_kind": apply_result.get("next_step_kind"),
            "pointer_confidence": apply_result.get("pointer_confidence"),
            "pointer_source": apply_result.get("pointer_source"),
            "incremental": bool((extract.get("incremental") or {}).get("is_incremental")),
            "window_count": len(extract.get("window_summaries") or []),
            "segment_count": len(extract.get("topic_segments") or []),
            "coverage_ratio": extract.get("coverage_ratio"),
            "decisions_extracted": int(extract.get("decisions_extracted") or 0),
            "decision_rejections": extract.get("decision_rejections") or {},
            "tokens_estimated": int(extract.get("tokens_estimated") or 0),
            "token_budget_exceeded": bool(extract.get("token_budget_exceeded")),
            "live_apply": bool(apply),
        },
    )
    record_boundary_distill(memory_home, chat_id)
    return {
        "status": "distilled",
        "chat_id": chat_id,
        "transcript": str(jsonl),
        "duration_ms": duration_ms,
        **merge_result,
    }


def run_boundary_distill(
    payload: dict[str, Any],
    *,
    memory_home: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
    strategy: str = "auto",
) -> dict[str, Any]:
    jsonl = resolve_transcript_jsonl(
        payload, memory_home=memory_home, projects_root=projects_root
    )
    if jsonl is None:
        _record_metric(
            memory_home,
            {
                "event": payload.get("hook_event_name", "boundary"),
                "status": "skipped",
                "reason": "no_transcript",
            },
        )
        return {"status": "skipped", "reason": "no_transcript"}

    chat_id = jsonl.stem
    event = str(payload.get("hook_event_name") or "boundary")

    if should_skip_debounce(memory_home, chat_id):
        _record_metric(
            memory_home,
            {
                "event": event,
                "status": "skipped",
                "chat_id": chat_id,
                "reason": "debounced",
            },
        )
        return {
            "status": "skipped",
            "reason": "debounced",
            "chat_id": chat_id,
            "transcript": str(jsonl),
        }

    skip = should_skip_boundary_distill(
        memory_home=memory_home, chat_id=chat_id, jsonl=jsonl
    )
    if skip:
        _record_metric(
            memory_home,
            {
                "event": event,
                "status": "skipped",
                "chat_id": chat_id,
                "reason": skip,
            },
        )
        return {
            "status": "skipped",
            "reason": skip,
            "chat_id": chat_id,
            "transcript": str(jsonl),
        }

    result = distill_jsonl(
        jsonl,
        memory_home=memory_home,
        projects_root=projects_root,
        strategy=strategy,
        event=event,
    )
    result["event"] = event
    return result


def run_session_start_catchup(
    payload: dict[str, Any],
    *,
    memory_home: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
    days: int = SESSION_START_DAYS,
    limit: int = SESSION_START_CATCHUP_LIMIT,
    strategy: str = "auto",
) -> dict[str, Any]:
    """Background distill for pending chats in open workspace(s)."""
    slugs = slugs_from_workspace_roots(payload.get("workspace_roots") or [])
    if not slugs:
        return {
            "status": "catchup",
            "distilled": 0,
            "skipped": 0,
            "errors": 0,
            "candidates": 0,
            "workspace_slugs": [],
            "results": [],
            "reason": "no_workspace_roots",
        }
    pending = list_chats_needing_distill(
        memory_home,
        projects_root=projects_root,
        days=days,
        workspace_slugs=slugs,
        limit=limit,
    )
    results: list[dict[str, Any]] = []
    distilled = 0
    skipped = 0
    errors = 0

    for row in pending:
        jsonl = row["jsonl"]
        chat_id = row["id"]
        out = distill_jsonl(
            jsonl,
            memory_home=memory_home,
            projects_root=projects_root,
            strategy=strategy,
            event="sessionStart",
        )
        results.append(out)
        if out.get("status") == "distilled":
            distilled += 1
        elif out.get("status") == "error":
            errors += 1
        elif out.get("status") == "skipped":
            skipped += 1

    _record_metric(
        memory_home,
        {
            "event": "sessionStart",
            "status": "catchup",
            "distilled": distilled,
            "skipped": skipped,
            "errors": errors,
            "candidates": len(pending),
        },
    )

    return {
        "status": "catchup",
        "distilled": distilled,
        "skipped": skipped,
        "errors": errors,
        "candidates": len(pending),
        "workspace_slugs": sorted(slugs),
        "results": results,
    }


def handle_session_start(
    payload: dict[str, Any],
    *,
    memory_home: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict[str, Any]:
    """sessionStart — first-run bootstrap, catch-up distill, pointer queue."""
    _record_metric(
        memory_home,
        {
            "event": "sessionStart",
            "status": "started",
            "workspace_slugs": sorted(
                slugs_from_workspace_roots(payload.get("workspace_roots") or [])
            ),
        },
    )
    from lib.first_run import handle_first_run, is_initialized

    first_run = handle_first_run(
        memory_home=memory_home,
        projects_root=projects_root,
        script_file=SCRIPT_DIR / "boundary-hooks.py",
    )
    result: dict[str, Any] = {}
    if first_run is not None:
        result["first_run"] = first_run

    fr_phase = (first_run or {}).get("first_run")
    if fr_phase in (
        "complete",
        "awaiting_scope",
        "awaiting_setup",
        "skipped_existing_data",
    ):
        if first_run and first_run.get("user_message"):
            result["user_message"] = first_run["user_message"]
        result["catchup"] = {"status": "skipped", "reason": fr_phase}
        return result

    if not is_initialized(memory_home):
        if first_run and first_run.get("user_message"):
            result["user_message"] = first_run["user_message"]
        result["catchup"] = {"status": "skipped", "reason": "first_run_pending"}
        return result

    slugs = slugs_from_workspace_roots(payload.get("workspace_roots") or [])
    catchup = run_session_start_catchup(
        payload, memory_home=memory_home, projects_root=projects_root
    )
    result["catchup"] = catchup

    live_result: dict[str, Any] = {"status": "skipped", "reason": "no_transcript"}
    jsonl = resolve_transcript_jsonl(
        payload, memory_home=memory_home, projects_root=projects_root
    )
    if jsonl is not None:
        chat_id = jsonl.stem
        if should_skip_debounce(memory_home, chat_id):
            live_result = {"status": "skipped", "reason": "debounced", "chat_id": chat_id}
        elif should_live_distill(memory_home, chat_id, jsonl):
            live_result = run_live_distill(
                distill_jsonl,
                jsonl,
                memory_home=memory_home,
                projects_root=projects_root,
            )
        else:
            live_result = {
                "status": "skipped",
                "reason": "already_distilled",
                "chat_id": chat_id,
            }
    result["live_distill"] = live_result

    try:
        result["pointer_feedback"] = log_session_start_pointer_feedback(
            memory_home,
            slugs,
            payload=payload,
            projects_root=projects_root,
        )
    except OSError:
        result["pointer_feedback"] = []

    msg = session_start_user_message(
        memory_home, payload.get("workspace_roots") or []
    )
    if msg:
        result["user_message"] = msg
    return result


def _session_end_user_message(distill: dict[str, Any]) -> str | None:
    if distill.get("status") != "distilled":
        return None
    apply_result = distill.get("apply_result") or {}
    kind = apply_result.get("next_step_kind")
    conf = float(apply_result.get("pointer_confidence") or 0.0)
    project_rel = distill.get("project_rel", "chats/projects/<slug>.md")
    if kind in ("placeholder_empty", "placeholder_stale"):
        return (
            f"[agent-memory] Curate ## Next step in {project_rel} — "
            "use templates/chats/pointer-curate-prompt.md + latest merge-staging."
        )
    if conf < POINTER_LOW_CONFIDENCE:
        return (
            f"[agent-memory] Low-confidence pointer ({conf:.2f}) in {project_rel} — "
            "curate ## Next step (pointer-curate-prompt.md)."
        )
    return None


def handle_boundary(
    payload: dict[str, Any],
    *,
    memory_home: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict[str, Any]:
    event = payload.get("hook_event_name", "")
    result: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    if event not in BOUNDARY_EVENTS:
        result["status"] = "ignored"
        return result

    chat_id = chat_id_from_payload(payload)
    _record_metric(
        memory_home,
        {
            "event": event,
            "status": "received",
            "chat_id": chat_id,
        },
    )

    distill = run_boundary_distill(
        payload, memory_home=memory_home, projects_root=projects_root
    )
    result["distill"] = distill

    if event == "sessionEnd" and distill.get("status") == "distilled":
        apply_result = distill.get("apply_result") or {}
        should_queue, reason = needs_enqueue(apply_result)
        if should_queue:
            enqueue_pointer(
                memory_home,
                chat_id=distill.get("chat_id") or chat_id or "unknown",
                project_rel=str(distill.get("project_rel") or "chats/projects/unknown.md"),
                reason=reason,
                workspace_slug=str(distill.get("slug") or ""),
                staging_path=str(distill.get("staging_path") or ""),
                pointer_confidence=apply_result.get("pointer_confidence"),
            )

    if event == "preCompact":
        from lib.agent_live_distill import build_precompact_user_message

        result["user_message"] = build_precompact_user_message(
            memory_home,
            distill,
            framework_root=SCRIPT_DIR.parent,
        )
    elif event == "sessionEnd":
        msg = _session_end_user_message(distill)
        if msg:
            result["user_message"] = msg

    return result


def dispatch(
    mode: str,
    payload: dict[str, Any],
    *,
    memory_home: Path | None = None,
    projects_root: Path | None = None,
) -> dict[str, Any]:
    hub = resolve_memory_home(
        str(memory_home) if memory_home else None,
        script_file=str(SCRIPT_DIR / "boundary-hooks.py"),
    )
    proot = (
        projects_root.expanduser().resolve()
        if projects_root
        else DEFAULT_PROJECTS_ROOT
    )
    if mode == "session-start":
        return handle_session_start(payload, memory_home=hub, projects_root=proot)
    if mode == "boundary":
        return handle_boundary(payload, memory_home=hub, projects_root=proot)
    raise ValueError(f"unknown mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("session-start", "boundary"),
        help="Hook handler mode",
    )
    parser.add_argument("--memory-home", help="MEMORY_HOME override")
    parser.add_argument("--projects-root", help="Cursor projects root")
    parser.add_argument(
        "--input",
        help="JSON file (default: stdin)",
    )
    parser.add_argument("-o", "--output", help="Write JSON result to file")
    args = parser.parse_args(argv)

    if args.input:
        raw = Path(args.input).expanduser().read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    if not raw.strip():
        print("Error: empty hook input", file=sys.stderr)
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        print("Error: hook input must be a JSON object", file=sys.stderr)
        return 1

    proot = (
        Path(args.projects_root).expanduser().resolve()
        if args.projects_root
        else None
    )
    hub = (
        resolve_memory_home(str(args.memory_home), script_file=str(SCRIPT_DIR / "boundary-hooks.py"))
        if args.memory_home
        else resolve_memory_home(None, script_file=str(SCRIPT_DIR / "boundary-hooks.py"))
    )
    try:
        result = dispatch(args.mode, payload, memory_home=hub, projects_root=proot)
    except Exception as exc:
        report_exception(
            hub,
            mode=args.mode,
            event=str(payload.get("hook_event_name") or args.mode),
            exc=exc,
        )
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    out = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
