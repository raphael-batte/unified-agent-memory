"""manifest.json helpers — shared by list-chats, distill-merge, memory-status."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.timestamps import now_iso, parse_distilled_at
from lib.transcript_cursor import (  # noqa: I001
    decode_workspace_folder_to_path,
    safe_path_component,
    workspace_slug,
)

_PROJECT_REL_RE = re.compile(r"projects/[A-Za-z0-9._-]+\.md")
_RECENT_UUID_RE = re.compile(
    r"\]\(([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\)"
)


def load_manifest(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"processed": [], "pending": []}


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def primary_project_rel(
    manifest: dict[str, Any],
    chat_id: str,
    *,
    workspace_slug: str,
    override: str | None = None,
) -> str:
    """
    Relative path under chats/ for the project markdown file.
    Prefers manifest distilled_to, then --project override, else workspace slug.
    """
    if override:
        raw = override.strip().lstrip("/")
        if raw.startswith("projects/"):
            raw = raw[len("projects/") :]
        if raw.endswith(".md"):
            raw = raw[: -len(".md")]
        return f"projects/{safe_path_component(raw, fallback='project')}.md"

    entry = processed_by_id(manifest).get(chat_id)
    if entry:
        for rel in entry.get("distilled_to") or []:
            # Only trust entries that are exactly projects/<safe-name>.md — a
            # crafted manifest must not redirect writes outside the hub.
            if isinstance(rel, str) and _PROJECT_REL_RE.fullmatch(rel):
                return rel

    return f"projects/{safe_path_component(workspace_slug, fallback='unknown')}.md"


def processed_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("processed", []):
        if isinstance(entry, dict) and entry.get("id"):
            out[str(entry["id"])] = entry
    return out


def upsert_processed(
    manifest: dict[str, Any],
    entry: dict[str, Any],
) -> bool:
    """Insert or update processed[] entry. Returns True if newly inserted."""
    uid = entry.get("id")
    if not uid:
        raise ValueError("manifest entry requires id")

    processed = manifest.setdefault("processed", [])
    if not isinstance(processed, list):
        raise ValueError("manifest processed must be a list")

    for i, existing in enumerate(processed):
        if isinstance(existing, dict) and existing.get("id") == uid:
            merged = {**existing, **entry}
            processed[i] = merged
            return False

    processed.append(entry)
    return True


def _entry_recency(entry: dict[str, Any]) -> tuple[Any, str]:
    """Sort key for choosing the newer manifest entry."""
    for key in ("distilled_at", "date"):
        raw = entry.get(key)
        if raw:
            parsed = parse_distilled_at(str(raw))
            if parsed is not None:
                return (parsed, str(raw))
            return (str(raw), str(raw))
    return ("", "")


def entry_is_newer(source: dict[str, Any], dest: dict[str, Any]) -> bool:
    """True if source entry should win over dest for the same chat id."""
    return _entry_recency(source) >= _entry_recency(dest)


def merge_pending_lists(
    *lists: list[Any],
) -> list[Any]:
    """Dedupe pending entries preserving order."""
    out: list[Any] = []
    seen: set[str] = set()
    for items in lists:
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                key = str(item.get("id") or json.dumps(item, sort_keys=True))
            else:
                key = str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def merge_manifests(
    source: dict[str, Any],
    dest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    """
    Merge two manifest dicts by chat id.
    Returns (merged_manifest, stats).
    """
    merged: dict[str, Any] = {}
    for key in ("_comment", "_schema"):
        if key in dest:
            merged[key] = dest[key]
        elif key in source:
            merged[key] = source[key]

    merged["processed"] = []
    merged["pending"] = merge_pending_lists(
        dest.get("pending") if isinstance(dest.get("pending"), list) else [],
        source.get("pending") if isinstance(source.get("pending"), list) else [],
    )

    dest_ids = processed_by_id(dest)
    source_ids = processed_by_id(source)
    stats = {
        "source_processed": len(source_ids),
        "dest_before": len(dest_ids),
        "added": 0,
        "updated": 0,
        "merged_total": 0,
    }

    all_ids = set(dest_ids) | set(source_ids)
    for uid in sorted(all_ids):
        src_entry = source_ids.get(uid)
        dst_entry = dest_ids.get(uid)
        if src_entry and dst_entry:
            if entry_is_newer(src_entry, dst_entry):
                upsert_processed(merged, {**dst_entry, **src_entry})
                stats["updated"] += 1
            else:
                upsert_processed(merged, {**src_entry, **dst_entry})
        elif src_entry:
            upsert_processed(merged, dict(src_entry))
            stats["added"] += 1
        elif dst_entry:
            upsert_processed(merged, dict(dst_entry))

    stats["merged_total"] = len(processed_by_id(merged))
    return merged, stats


def count_project_distills(memory_home: Path) -> int:
    """Count non-example project distill files with content beyond a stub."""
    projects = memory_home / "chats" / "projects"
    if not projects.is_dir():
        return 0
    count = 0
    for path in projects.glob("*.md"):
        if path.name == "example.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text.strip()) > 80 and "## Recent" in text:
            count += 1
    return count


def manifest_desync_warning(memory_home: Path) -> str | None:
    """Return warning text when manifest registry disagrees with on-disk distills."""
    manifest_path = memory_home / "chats" / "manifest.json"
    processed, _, _ = count_chats(manifest_path)
    n_distills = count_project_distills(memory_home)
    if processed == 0 and n_distills >= 2:
        return (
            f"manifest desync: processed=0 but {n_distills} project distills on disk "
            "(run memory-doctor.py --rebuild-manifest)"
        )
    if processed > 0 and n_distills > processed + 5:
        return (
            f"manifest may be incomplete: processed={processed}, "
            f"project distills≈{n_distills}"
        )
    return None


def rebuild_manifest_from_hub(memory_home: Path) -> tuple[dict[str, Any], dict[str, int]]:
    """
    Best-effort rebuild of processed[] from hub artifacts (extracts + project Recent).
    """
    manifest_path = memory_home / "chats" / "manifest.json"
    manifest = load_manifest(manifest_path)
    stats = {"from_extracts": 0, "from_recent": 0, "skipped": 0}

    extracts_dir = memory_home / "chats" / "extracts"
    if extracts_dir.is_dir():
        for path in sorted(extracts_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                stats["skipped"] += 1
                continue
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            chat_id = str(data.get("uuid") or path.stem)
            workspace = str(data.get("workspace") or "unknown")
            slug = str(data.get("workspace_slug") or workspace_slug(workspace))
            summary = str(data.get("first_query") or data.get("summary") or "")[:140]
            rel = f"projects/{safe_path_component(slug, fallback='unknown')}.md"
            entry = make_processed_entry(
                chat_id=chat_id,
                workspace=workspace,
                transcript_date=str(data.get("date") or now_iso()[:10]),
                summary=summary or chat_id[:8],
                distilled_to=[rel],
                workspace_path=data.get("workspace_path"),
            )
            upsert_processed(manifest, entry)
            stats["from_extracts"] += 1

    projects_dir = memory_home / "chats" / "projects"
    if projects_dir.is_dir():
        for proj in sorted(projects_dir.glob("*.md")):
            if proj.name == "example.md":
                continue
            slug = proj.stem
            rel = f"projects/{proj.name}"
            text = proj.read_text(encoding="utf-8", errors="replace")
            seen_in_file: set[str] = set()
            for match in _RECENT_UUID_RE.finditer(text):
                chat_id = match.group(1)
                if chat_id in seen_in_file:
                    continue
                seen_in_file.add(chat_id)
                if chat_id in processed_by_id(manifest):
                    continue
                entry = make_processed_entry(
                    chat_id=chat_id,
                    workspace=f"Users-x-Work-{slug}",
                    transcript_date=now_iso()[:10],
                    summary=f"from {rel} Recent",
                    distilled_to=[rel],
                )
                upsert_processed(manifest, entry)
                stats["from_recent"] += 1

    stats["merged_total"] = len(processed_by_id(manifest))
    return manifest, stats


def make_processed_entry(
    *,
    chat_id: str,
    workspace: str,
    transcript_date: str,
    summary: str,
    distilled_to: list[str],
    distilled_at: str | None = None,
    transcript_available: bool | None = None,
    workspace_path: str | None = None,
    watermark_user_count: int | None = None,
    watermark_tail_hash: str | None = None,
    pointer_source: str | None = None,
    pointer_set_at: str | None = None,
) -> dict[str, Any]:
    today = distilled_at or now_iso()
    slug = workspace_slug(workspace)
    target = f"projects/{slug}.md"
    if target not in distilled_to:
        distilled_to = [target, *distilled_to]
    resolved_path = workspace_path or decode_workspace_folder_to_path(workspace)
    entry: dict[str, Any] = {
        "id": chat_id,
        "workspace": workspace,
        "date": transcript_date,
        "distilled_at": today,
        "distilled_to": distilled_to,
        "summary": summary[:140],
    }
    if resolved_path:
        entry["workspace_path"] = resolved_path
    if transcript_available is not None:
        entry["transcript_available"] = transcript_available
    if watermark_user_count is not None:
        entry["watermark_user_count"] = watermark_user_count
    if watermark_tail_hash:
        entry["watermark_tail_hash"] = watermark_tail_hash
    if pointer_source:
        entry["pointer_source"] = pointer_source
    if pointer_set_at:
        entry["pointer_set_at"] = pointer_set_at
    return entry


def count_chats(
    manifest_path: Path,
    *,
    total_transcripts: int | None = None,
) -> tuple[int, int, int]:
    """
    Return (processed_count, pending_count, total).
    pending = total - processed_ids if total_transcripts given, else len(pending list).
    """
    if not manifest_path.is_file():
        return 0, 0, total_transcripts or 0

    manifest = load_manifest(manifest_path)
    processed_ids = {p.get("id") for p in manifest.get("processed", []) if isinstance(p, dict)}
    processed_ids.discard(None)
    n_processed = len(processed_ids)

    if total_transcripts is not None:
        return n_processed, max(0, total_transcripts - n_processed), total_transcripts

    pending_list = manifest.get("pending", [])
    n_pending = len(pending_list) if isinstance(pending_list, list) else 0
    return n_processed, n_pending, n_processed + n_pending
