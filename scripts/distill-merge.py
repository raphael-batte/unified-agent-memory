#!/usr/bin/env python3
"""Merge distill extract into manifest + staging markdown (preserve chat language)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.chats_manifest import (  # noqa: E402
    load_manifest,
    make_processed_entry,
    primary_project_rel,
    processed_by_id,
    save_manifest,
    upsert_processed,
)
from lib.distill_watermark import watermark_for_manifest  # noqa: E402
from lib.distill_map import write_map_staging  # noqa: E402
from lib.rolling_distill import update_rolling_after_merge  # noqa: E402
from lib.apply_guard import check_cli_apply_guard  # noqa: E402
from lib.defaults import APPLY_REVIEW_MAX_DAYS  # noqa: E402
from lib.distill_links import enrich_extract, recent_bullet  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.agent_live_distill import enrich_extract_with_agent_live  # noqa: E402
from lib.novelty import collect_prior_texts, filter_novel_items  # noqa: E402
from lib.project_merge import apply_extract_to_project  # noqa: E402
from lib.timestamps import now_iso, staging_date_slug  # noqa: E402
from lib.transcript import find_transcript, workspace_slug  # noqa: E402
from lib.transcript_cursor import safe_path_component  # noqa: E402

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"


def load_extract(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_staging_markdown(
    extract: dict,
    *,
    project_rel: str,
    project_path: Path | None = None,
) -> str:
    """Staging file for agent merge — verbatim user messages, no translation."""
    slug = extract.get("workspace_slug", "unknown")
    uid = extract.get("uuid", "?")
    today = now_iso()
    keywords = ", ".join(extract.get("keywords_hit") or []) or "—"
    prior_texts = collect_prior_texts(project_path)
    msgs = filter_novel_items(extract.get("user_messages") or [], prior_texts)

    summary_bullets = extract.get("summary_bullets") or []
    summary_block = ""
    if summary_bullets:
        summary_block = "\n".join(f"- {b}" for b in summary_bullets[:5])
    else:
        summary_block = (
            extract.get("final_summary") or extract.get("first_query") or "(no summary)"
        )[:500]

    lines = [
        f"# Distill staging — {slug}",
        f"_Generated: {today} · uuid: {uid}_",
        "",
        f"> Agent merge into `chats/{project_rel}` — preserve language; no secrets.",
        "> ## Decisions are curated by agent/LLM — do not copy raw bullets verbatim.",
        "",
        "## Summary",
        "",
        summary_block,
        "",
    ]
    cov = extract.get("coverage_ratio")
    if cov is not None:
        lines.extend(
            [
                f"_Coverage: {cov:.1%} of {extract.get('user_message_count', '?')} user msgs_",
                "",
            ]
        )
    agent_live = extract.get("agent_live") or {}
    if agent_live.get("summary_bullets"):
        lines.extend(["", "## Agent live summary (preCompact)", ""])
        for bullet in agent_live["summary_bullets"][:5]:
            lines.append(f"- {bullet}")
    if agent_live.get("next_step"):
        lines.extend(
            [
                "",
                "## Agent live next step candidate",
                "",
                f"- {agent_live['next_step']}",
            ]
        )

    initial = extract.get("first_query")
    if initial and extract.get("final_summary"):
        lines.extend(
            [
                "### Initial request",
                "",
                str(initial)[:240],
                "",
            ]
        )
    lines.extend(
        [
            "## Raw candidates (review — not Decisions)",
            "",
        ]
    )
    for msg in msgs[:8]:
        snippet = msg.strip()
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        if snippet:
            lines.append(f"- {snippet}")

    rolling = filter_novel_items(extract.get("rolling_summary") or [], prior_texts)
    if rolling:
        lines.extend(["", "## Rolling summary (incremental)", ""])
        for bullet in rolling[:8]:
            lines.append(f"- {bullet}")

    segments = extract.get("topic_segments") or []
    if segments:
        lines.extend(["", "## Topic segments", ""])
        for seg in segments[:8]:
            if not isinstance(seg, dict):
                continue
            sid = seg.get("segment", "?")
            head = (
                f"- s{sid}: {seg.get('count', 0)} msgs — {seg.get('preview', '')}"
            )
            lines.append(head)
            for bullet in seg.get("bullets") or []:
                lines.append(f"  - {bullet}")

    decisions = extract.get("decision_candidates") or []
    if decisions:
        lines.extend(["", "## Decision candidates (extracted)", ""])
        for row in decisions[:8]:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if text:
                src = row.get("source", "?")
                lines.append(f"- [{src}] {text[:240]}")

    snippets = extract.get("assistant_snippets") or []
    if snippets:
        lines.extend(["", "## Assistant snippets (selective)", ""])
        for snip in snippets[:5]:
            lines.append(f"- {snip}")

    open_todos = extract.get("open_todos") or []
    if open_todos:
        lines.extend(["", "## Open todos (TodoWrite)", ""])
        for row in open_todos[:8]:
            if not isinstance(row, dict):
                continue
            status = row.get("status", "?")
            content = str(row.get("content") or "").strip()
            if content:
                lines.append(f"- [{status}] {content[:200]}")

    lines.extend(
        [
            "",
            "## Open threads (candidates)",
            "",
            "- ",
            "",
            "## Recent",
            "",
            f"- {recent_bullet(extract, today)}",
            "",
        ]
    )
    return "\n".join(lines)


def append_pointer_candidate(staging_md: str, candidate: str | None) -> str:
    if not candidate:
        return staging_md
    return (
        staging_md.rstrip()
        + "\n\n## Pointer candidate (not applied — curated Next step preserved)\n\n"
        + f"- {candidate}\n"
    )


def run_merge(
    *,
    memory_home: Path,
    chat_id: str,
    extract: dict,
    dry_run: bool = False,
    apply: bool = False,
    force_apply: bool = False,
    review_max_days: int = APPLY_REVIEW_MAX_DAYS,
    bootstrap_decisions: bool = False,
    project_override: str | None = None,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict:
    manifest_path = memory_home / "chats" / "manifest.json"
    manifest = load_manifest(manifest_path)

    extract = enrich_extract(
        extract,
        memory_home=memory_home,
        projects_root=projects_root,
    )
    extract = enrich_extract_with_agent_live(
        extract, memory_home=memory_home, chat_id=chat_id
    )

    slug = safe_path_component(
        extract.get("workspace_slug") or workspace_slug(extract.get("workspace", "")),
        fallback="unknown",
    )
    safe_id = safe_path_component(chat_id, fallback="chat")
    project_rel = primary_project_rel(
        manifest,
        chat_id,
        workspace_slug=slug,
        override=project_override,
    )

    existing = processed_by_id(manifest).get(chat_id)
    if existing and existing.get("distilled_to"):
        distilled_to = list(existing["distilled_to"])
        if project_rel not in distilled_to:
            distilled_to.insert(0, project_rel)
    else:
        distilled_to = [project_rel]

    source = extract.get("source_path")
    wm = (
        watermark_for_manifest(Path(str(source)).expanduser())
        if source
        else {"user_message_count": extract.get("user_message_count"), "tail_hash": ""}
    )
    entry = make_processed_entry(
        chat_id=chat_id,
        workspace=extract.get("workspace", "unknown"),
        transcript_date=extract.get("date", datetime.now().strftime("%Y-%m-%d")),
        summary=extract.get("first_query", ""),
        distilled_to=distilled_to,
        transcript_available=bool(extract.get("transcript_available")),
        watermark_user_count=int(wm.get("user_message_count") or 0),
        watermark_tail_hash=str(wm.get("tail_hash") or ""),
    )

    project_path = memory_home / "chats" / project_rel
    staging_dir = memory_home / "chats" / "merge-staging"
    staging_path = (
        staging_dir / f"{slug}-{staging_date_slug(entry['distilled_at'])}-{safe_id[:8]}.md"
    )
    staging_md = build_staging_markdown(
        extract, project_rel=project_rel, project_path=project_path
    )

    result = {
        "chat_id": chat_id,
        "slug": slug,
        "project_rel": project_rel,
        "manifest_path": str(manifest_path),
        "staging_path": str(staging_path),
        "project_file": str(project_path),
        "distilled_at": entry["distilled_at"],
        "inserted": True,
        "dry_run": dry_run,
        "applied": False,
    }

    if dry_run:
        result["staging_preview_lines"] = len(staging_md.splitlines())
        if apply:
            result["apply_preview"] = (
                f"would update Recent in {result['project_file']} (no Decisions)"
            )
        return result

    if apply and not force_apply:
        block = check_cli_apply_guard(
            memory_home,
            chat_id,
            project_path,
            manifest,
            max_age_days=review_max_days,
        )
        if block:
            result["status"] = "blocked"
            result["block_reason"] = block
            return result

    inserted = upsert_processed(manifest, entry)
    result["inserted"] = inserted
    save_manifest(manifest_path, manifest)

    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path.write_text(staging_md, encoding="utf-8")

    map_path = write_map_staging(memory_home, extract)
    if map_path is not None:
        result["map_staging_path"] = str(map_path)

    extracts_dir = memory_home / "chats" / "extracts"
    extracts_dir.mkdir(parents=True, exist_ok=True)
    (extracts_dir / f"{safe_id}.json").write_text(
        json.dumps(extract, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if apply:
        result["applied"] = True
        apply_result = apply_extract_to_project(
            project_path,
            extract,
            today=entry["distilled_at"],
            bootstrap_decisions=bootstrap_decisions,
            memory_home=memory_home,
            manifest_entry=existing,
        )
        result["apply_result"] = apply_result
        if apply_result.get("pointer_preserved_curated") and apply_result.get(
            "pointer_candidate"
        ):
            staging_path.write_text(
                append_pointer_candidate(
                    staging_path.read_text(encoding="utf-8"),
                    str(apply_result["pointer_candidate"]),
                ),
                encoding="utf-8",
            )
        if apply_result.get("next_step_kind") == "extracted":
            entry["pointer_source"] = apply_result.get("pointer_provenance", "auto")
            entry["pointer_set_at"] = entry["distilled_at"]
            upsert_processed(manifest, entry)
            save_manifest(manifest_path, manifest)

    inc = extract.get("incremental") or {}
    if inc.get("incremental_count"):
        update_rolling_after_merge(
            memory_home,
            chat_id,
            total_user_count=int(extract.get("user_message_count") or 0),
            incremental_bullets=inc.get("incremental_bullets"),
            incremental_from=int(inc.get("incremental_from") or 0),
            workspace_slug=str(extract.get("workspace_slug") or slug),
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uuid", help="Chat transcript uuid")
    parser.add_argument("--memory-home", help="Hub path override")
    parser.add_argument("--extract", metavar="JSON", help="Use existing extract JSON")
    parser.add_argument(
        "--strategy",
        default="auto",
        choices=("tail", "spread", "all", "auto"),
    )
    parser.add_argument("--projects-root", metavar="DIR")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Recent≤3 + ## Next step; optional [bootstrap] Decisions when empty",
    )
    parser.add_argument(
        "--force-apply",
        action="store_true",
        help="Skip apply guard (hooks use this internally)",
    )
    parser.add_argument(
        "--review-max-days",
        type=int,
        default=APPLY_REVIEW_MAX_DAYS,
        metavar="N",
        help=f"Apply guard: block CLI --apply when curated Decisions older than N days (default {APPLY_REVIEW_MAX_DAYS})",
    )
    parser.add_argument(
        "--bootstrap-decisions",
        action="store_true",
        help="Seed ## Decisions from keyword-tagged user messages when section is empty",
    )
    parser.add_argument(
        "--project",
        metavar="REL",
        help="Target project file (e.g. example-app or projects/example-app.md)",
    )
    parser.add_argument("-o", "--output", metavar="FILE", help="Write result JSON")
    args = parser.parse_args()

    memory_home = resolve_memory_home(args.memory_home, script_file=__file__)
    chat_id = args.uuid.strip()

    if args.extract:
        extract_path = Path(args.extract).expanduser().resolve()
        if not extract_path.is_file():
            print(f"Error: extract not found: {extract_path}", file=sys.stderr)
            return 1
        extract = load_extract(extract_path)
    else:
        de = load_script_module("distill_extract", "distill-extract.py")
        projects_root = (
            Path(args.projects_root).expanduser().resolve()
            if args.projects_root
            else DEFAULT_PROJECTS_ROOT
        )
        jsonl = find_transcript(
            chat_id, projects_root, memory_home=memory_home
        )
        if jsonl is None:
            print(f"Error: transcript not found: {chat_id}", file=sys.stderr)
            return 1
        manifest = load_manifest(memory_home / "chats" / "manifest.json")
        manifest_entry = processed_by_id(manifest).get(chat_id)
        extract = de.build_extract(
            jsonl,
            projects_root=projects_root,
            strategy=args.strategy,
            memory_home=memory_home,
            manifest_entry=manifest_entry,
        )

    result = run_merge(
        memory_home=memory_home,
        chat_id=chat_id,
        extract=extract,
        dry_run=args.dry_run,
        apply=args.apply,
        force_apply=args.force_apply,
        review_max_days=args.review_max_days,
        bootstrap_decisions=args.bootstrap_decisions,
        project_override=args.project,
    )

    out = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)

    if result.get("status") == "blocked":
        print(f"WARNING: {result.get('block_reason')}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"dry-run: would write {result['staging_path']}", file=sys.stderr)
    else:
        msg = f"manifest updated; staging: {result['staging_path']}"
        if result.get("applied"):
            ar = result.get("apply_result", {})
            msg += f"; applied → {ar.get('project_file')} (Recent + Next step)"
        print(msg, file=sys.stderr)
    return 0


def load_script_module(module_name: str, filename: str):
    import importlib.util

    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    sys.exit(main())
