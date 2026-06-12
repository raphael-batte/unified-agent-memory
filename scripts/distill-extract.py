#!/usr/bin/env python3
"""Extract structured chat summary from Cursor jsonl — for agent distill (not raw jsonl)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.assistant_snippets import extract_assistant_snippets_from_parsed  # noqa: E402
from lib.transcript_parse import parse_transcript  # noqa: E402
from lib.defaults import (  # noqa: E402
    AUTO_SPREAD_THRESHOLD,
    DEFAULT_KEYWORDS,
    DISTILL_TOKEN_BUDGET,
    MAP_REDUCE_THRESHOLD,
    MAP_REDUCE_WINDOW_SIZE,
    MAX_DISTILL_MESSAGES,
    load_thresholds,
)
from lib.decision_extract import extract_decision_candidates  # noqa: E402
from lib.message_importance import mechanical_bullets, trim_message  # noqa: E402
from lib.segment_selection import (  # noqa: E402
    build_summary_bullets,
    coverage_ratio,
    select_per_segment,
)
from lib.topic_segmentation import segment_messages  # noqa: E402
from lib.token_budget import select_by_importance, window_messages  # noqa: E402
from lib.secrets_guard import is_terminal_noise, sanitize_message  # noqa: E402
from lib.transcript import (  # noqa: E402
    TranscriptSchemaError,
    extract_raw_user_texts,
    find_transcript,
    workspace_from_path,
    workspace_slug,
)
from lib.transcript_cursor import is_redacted_or_noise, normalize_user_text  # noqa: E402

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"

KEYWORDS = DEFAULT_KEYWORDS
STRATEGIES = ("importance", "tail", "spread", "all", "auto")


def resolve_strategy(
    strategy: str,
    total: int,
    *,
    auto_spread_threshold: int = AUTO_SPREAD_THRESHOLD,
) -> str:
    if strategy == "auto":
        return "importance"
    if strategy == "importance":
        return "importance"
    return strategy


def select_tail(messages: list[str], max_messages: int) -> list[str]:
    if len(messages) <= max_messages:
        return messages
    head = messages[:1]
    tail_n = max_messages - len(head)
    return head + messages[-tail_n:]


def select_spread(messages: list[str], max_messages: int) -> list[str]:
    total = len(messages)
    if total <= max_messages:
        return messages
    third = max_messages // 3
    head_n = third
    mid_n = third
    tail_n = max_messages - head_n - mid_n
    head = messages[:head_n]
    tail = messages[-tail_n:] if tail_n else []
    middle_pool = messages[head_n : total - tail_n] if tail_n else messages[head_n:]
    if not middle_pool:
        return head + tail
    if len(middle_pool) <= mid_n:
        mid = middle_pool
    else:
        step = len(middle_pool) / mid_n
        mid = [middle_pool[int(i * step)] for i in range(mid_n)]
    return head + mid + tail


def select_messages(
    messages: list[str],
    max_messages: int,
    strategy: str,
    *,
    token_budget: int = DISTILL_TOKEN_BUDGET,
    max_chars: int | None = None,
) -> list[str]:
    if strategy in ("importance", "auto"):
        picked = select_by_importance(
            messages,
            max_messages=max_messages,
            token_budget=token_budget,
            max_chars=max_chars,
        )
        if picked:
            return picked
        return select_tail(messages, max_messages)
    if strategy == "spread":
        return select_spread(messages, max_messages)
    return select_tail(messages, max_messages)


def build_window_summaries(
    messages: list[str],
    *,
    window_size: int = MAP_REDUCE_WINDOW_SIZE,
) -> list[dict]:
    """Map-reduce windows — mechanical bullets per window for staging."""
    windows = window_messages(messages, window_size=window_size)
    out: list[dict] = []
    for i, chunk in enumerate(windows, start=1):
        bullets = mechanical_bullets(chunk, max_items=3)
        if bullets:
            out.append({"window": i, "messages": len(chunk), "bullets": bullets})
    return out


def parse_user_messages(jsonl: Path) -> tuple[list[str], int, str]:
    parsed = parse_transcript(jsonl)
    raw_texts = parsed.user_texts()
    adapter = parsed.adapter
    all_msgs: list[str] = []
    secrets_redacted = 0
    for text in raw_texts:
        clean, n = sanitize_message(text)
        secrets_redacted += n
        if clean is None:
            continue
        if is_terminal_noise(clean):
            continue
        all_msgs.append(clean)
    if not all_msgs:
        raise TranscriptSchemaError(
            f"no usable user messages after sanitization: {jsonl}"
        )
    return all_msgs, secrets_redacted, adapter


def extract_user_messages(
    jsonl: Path,
    *,
    max_messages: int | None = MAX_DISTILL_MESSAGES,
    strategy: str = "tail",
) -> tuple[list[str], int, str, int, str]:
    all_msgs, secrets_redacted, adapter = parse_user_messages(jsonl)
    total = len(all_msgs)
    effective = resolve_strategy(strategy, total)

    if effective == "all" or max_messages is None:
        return all_msgs, total, "all", secrets_redacted, adapter
    if max_messages <= 0:
        return [], total, effective, secrets_redacted, adapter
    if total <= max_messages:
        return all_msgs, total, effective, secrets_redacted, adapter
    return (
        select_messages(all_msgs, max_messages, effective),
        total,
        effective,
        secrets_redacted,
        adapter,
    )


def keywords_hit(messages: list[str]) -> list[str]:
    blob = " ".join(messages).lower()
    return [kw for kw in KEYWORDS if kw in blob]


def build_extract(
    jsonl: Path,
    *,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
    max_messages: int | None = MAX_DISTILL_MESSAGES,
    strategy: str = "tail",
    memory_home: Path | None = None,
    manifest_entry: dict | None = None,
) -> dict:
    from lib.memory_config import load_hub_config  # noqa: E402
    from lib.token_budget import estimate_tokens  # noqa: E402

    thresholds = load_thresholds(
        load_hub_config(memory_home) if memory_home is not None else None
    )
    token_budget = int(thresholds["distill_token_budget"])
    map_reduce_threshold = int(thresholds["map_reduce_threshold"])
    map_window_size = int(thresholds["map_reduce_window_size"])
    auto_spread_threshold = int(thresholds["auto_spread_threshold"])
    segment_max = int(thresholds["segment_max"])
    segment_min_messages = int(thresholds["segment_min_messages"])
    message_max_chars = int(thresholds["message_select_max_chars"])
    max_decision_candidates = int(thresholds["max_decision_candidates"])
    summary_bullets_max = int(thresholds["summary_bullets_max"])
    if max_messages is None:
        max_messages = int(thresholds["max_distill_messages"])

    parsed = parse_transcript(jsonl)
    all_msgs: list[str] = []
    all_timestamps: list[str | None] = []
    secrets_redacted = 0
    for msg in parsed.user_messages:
        clean, n = sanitize_message(msg.text)
        secrets_redacted += n
        if clean is None:
            continue
        if is_terminal_noise(clean):
            continue
        all_msgs.append(clean)
        all_timestamps.append(msg.timestamp)
    if not all_msgs:
        raise TranscriptSchemaError(
            f"no usable user messages after sanitization: {jsonl}"
        )
    adapter = parsed.adapter
    total = len(all_msgs)
    effective = resolve_strategy(
        strategy, total, auto_spread_threshold=auto_spread_threshold
    )

    topic_segments = (
        segment_messages(
            all_msgs,
            timestamps=all_timestamps,
            max_segments=segment_max,
            min_segment_msgs=segment_min_messages,
            pause_minutes=int(thresholds["segment_pause_minutes"]),
            jaccard_window=int(thresholds["segment_jaccard_window"]),
            jaccard_min=float(thresholds["segment_jaccard_min"]),
            memory_home=memory_home,
        )
        if total >= 20
        else []
    )

    if effective == "all":
        messages = [trim_message(m, max_chars=message_max_chars) for m in all_msgs]
    elif max_messages <= 0:
        messages = []
    elif (
        topic_segments
        and total >= map_reduce_threshold
        and effective in ("importance", "auto")
    ):
        messages, topic_segments = select_per_segment(
            all_msgs,
            topic_segments,
            max_messages=max_messages,
            token_budget=token_budget,
            max_chars=message_max_chars,
        )
    elif total <= max_messages:
        messages = [trim_message(m, max_chars=message_max_chars) for m in all_msgs]
    else:
        messages = select_messages(
            all_msgs,
            max_messages,
            effective,
            token_budget=token_budget,
            max_chars=message_max_chars,
        )

    workspace = workspace_from_path(jsonl, projects_root)
    st = jsonl.stat()
    truncated = effective != "all" and total > len(messages)
    first_query = messages[0][:140] if messages else "(no user text)"
    final_summary = parsed.last_assistant_summary()
    assistant_snippets = extract_assistant_snippets_from_parsed(parsed)
    # window_summaries deprecated — topic segment bullets replace map-reduce windows.
    window_summaries: list[dict] = []
    summary_bullets = build_summary_bullets(
        topic_segments,
        final_assistant=final_summary,
        max_bullets=summary_bullets_max,
    )
    decision_candidates, decision_rejections = extract_decision_candidates(
        all_msgs,
        topic_segments,
        memory_home=memory_home,
        max_items=max_decision_candidates,
    )
    tokens_estimated = sum(estimate_tokens(m) for m in messages)
    open_todo_items = parsed.open_todos()
    from lib.transcript_stats import transcript_watermark  # noqa: E402

    wm = transcript_watermark(jsonl)

    incremental: dict | None = None
    if memory_home is not None:
        from lib.rolling_distill import build_incremental  # noqa: E402

        incremental = build_incremental(
            all_msgs,
            memory_home=memory_home,
            chat_id=jsonl.stem,
            manifest_entry=manifest_entry,
        )

    payload: dict = {
        "uuid": jsonl.stem,
        "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
        "workspace": workspace,
        "workspace_slug": workspace_slug(workspace),
        "first_query": first_query,
        "final_summary": final_summary,
        "user_messages": messages,
        "user_message_count": total,
        "strategy": effective,
        "truncated": truncated,
        "keywords_hit": keywords_hit(messages),
        "secrets_redacted": secrets_redacted,
        "source_path": str(jsonl.resolve()),
        "size_bytes": st.st_size,
        "transcript_adapter": adapter,
        "assistant_snippets": assistant_snippets,
        "window_summaries": window_summaries,
        "topic_segments": topic_segments,
        "summary_bullets": summary_bullets,
        "decision_candidates": decision_candidates,
        "coverage_ratio": coverage_ratio(len(messages), total),
        "decisions_extracted": len(decision_candidates),
        "decision_rejections": decision_rejections,
        "open_todos": [
            {"id": t.id, "content": t.content, "status": t.status} for t in open_todo_items
        ],
        "all_todos_completed": parsed.all_todos_completed,
        "watermark_user_count": int(wm.get("user_message_count") or 0),
        "watermark_tail_hash": str(wm.get("tail_hash") or ""),
        "tokens_estimated": tokens_estimated,
        "token_budget": token_budget,
        "token_budget_exceeded": tokens_estimated > token_budget,
    }
    if incremental:
        payload["incremental"] = incremental
        if incremental.get("rolling_summary"):
            payload["rolling_summary"] = incremental["rolling_summary"]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uuid", nargs="?", help="Chat transcript uuid")
    parser.add_argument("--path", metavar="JSONL", help="Direct path to .jsonl")
    parser.add_argument(
        "--max-messages",
        type=int,
        default=MAX_DISTILL_MESSAGES,
        metavar="N",
    )
    parser.add_argument(
        "--strategy",
        choices=STRATEGIES,
        default="auto",
        help="auto/importance=ranked sample; tail/spread=positional; all=full chat",
    )
    parser.add_argument("--all", action="store_true", help="Alias for --strategy all")
    parser.add_argument("--projects-root", metavar="DIR")
    parser.add_argument("--memory-home", help="Hub path (for transcripts/ fallback)")
    parser.add_argument("-o", "--output", metavar="FILE")
    args = parser.parse_args()

    projects_root = (
        Path(args.projects_root).expanduser().resolve()
        if args.projects_root
        else DEFAULT_PROJECTS_ROOT
    )
    memory_home = None
    if args.memory_home:
        from lib.memory_config import resolve_memory_home  # noqa: E402

        memory_home = resolve_memory_home(args.memory_home, script_file=__file__)

    try:
        if args.path:
            jsonl = Path(args.path).expanduser().resolve()
            if not jsonl.is_file():
                print(f"Error: not a file: {jsonl}", file=sys.stderr)
                return 1
        elif args.uuid:
            jsonl = find_transcript(
                args.uuid, projects_root, memory_home=memory_home
            )
            if jsonl is None:
                print(f"Error: transcript not found for uuid: {args.uuid}", file=sys.stderr)
                return 1
        else:
            parser.print_help()
            return 1

        strategy = "all" if args.all else args.strategy
        data = build_extract(
            jsonl,
            projects_root=projects_root,
            max_messages=args.max_messages,
            strategy=strategy,
        )
    except TranscriptSchemaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
