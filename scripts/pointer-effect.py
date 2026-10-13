#!/usr/bin/env python3
"""Is the forward pointer used? Snapshot threads, score due chats, print a report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.distill_metrics import read_metrics  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.pointer_effect import evaluate_backlog, record_snapshot, summarize  # noqa: E402


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home")
    parser.add_argument(
        "--cron",
        action="store_true",
        help="Snapshot Open threads and score chats that are due (cron pass)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)

    if args.cron:
        out = {"snapshot": record_snapshot(memory_home), **evaluate_backlog(memory_home)}
        print(json.dumps(out))
        return 0

    summary = summarize(read_metrics(memory_home, max_lines=20000))
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print("Pointer effect (Open threads → what the session did)")
    print(f"  Sessions scored: {summary['sessions']}")
    if not summary["sessions"]:
        print("  No scored sessions yet — data accrues as chats run.")
        return 0
    print(
        f"  Followed {_pct(summary['followed_rate'])} · "
        f"partial {_pct(summary['partial_rate'])} · "
        f"new topic {_pct(summary['new_topic_rate'])}"
    )
    print(
        f"  Curated threads followed {_pct(summary['curated_followed_rate'])} "
        f"(n={summary['curated_sessions']}) · [auto] {_pct(summary['auto_followed_rate'])} "
        f"(n={summary['auto_sessions']})"
    )
    print(
        f"  Blind resumes: {summary['blind_resumes']} · followed "
        f"{_pct(summary['blind_followed_rate'])}"
    )
    print(f"  Memory-miss cues: {_pct(summary['memory_miss_rate'])} of sessions")
    for env, row in summary["by_env"].items():
        print(f"  {env}: n={row['n']} · followed {_pct(row['followed_rate'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
