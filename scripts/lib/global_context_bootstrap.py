"""Bootstrap GLOBAL_CONTEXT Projects table from distill manifest."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.timestamps import now_iso, parse_distilled_at
from lib.transcript_cursor import decode_workspace_folder_to_path, workspace_slug

PROJECTS_TABLE_RE = re.compile(
    r"(##\s*Projects\s*\n)(\|[^\n]+\|\n\|[-| :]+\|\n)((?:\|[^\n]+\|\n)*)",
    re.IGNORECASE,
)


def repo_path_for_manifest_entry(entry: dict[str, Any]) -> str:
    """Resolved repo path from manifest entry — no hardcoded parent folders."""
    stored = str(entry.get("workspace_path", "")).strip()
    if stored:
        return stored
    workspace = str(entry.get("workspace", "unknown"))
    decoded = decode_workspace_folder_to_path(workspace)
    if decoded:
        return decoded
    slug = workspace_slug(workspace)
    return f"({slug})"


def collect_projects_from_manifest(
    manifest: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """slug -> {path, summary, status}."""
    by_slug: dict[str, dict[str, str]] = {}
    for entry in manifest.get("processed", []):
        if not isinstance(entry, dict):
            continue
        workspace = str(entry.get("workspace", "unknown"))
        slug = workspace_slug(workspace)
        summary = str(entry.get("summary", ""))[:80] or "—"
        path = repo_path_for_manifest_entry(entry)
        at = parse_distilled_at(str(entry.get("distilled_at", "")))
        at_ts = at.timestamp() if at else 0.0
        existing = by_slug.get(slug)
        if existing is None or at_ts >= existing.get("_distilled_ts", 0.0):
            by_slug[slug] = {
                "slug": slug,
                "path": path,
                "summary": summary,
                "status": "active",
                "_distilled_ts": at_ts,
            }
    for item in by_slug.values():
        item.pop("_distilled_ts", None)
    return by_slug


def format_project_row(item: dict[str, str]) -> str:
    return (
        f"| {item['slug']} | `{item['path']}` | {item['status']} | "
        f"{item['summary']} |"
    )


def merge_projects_table(
    text: str,
    projects: dict[str, dict[str, str]],
    *,
    merge_existing: bool = True,
) -> tuple[str, int]:
    """
    Update ## Projects table. Returns (new_text, rows_written).
    merge_existing: keep rows whose slug is not in projects.
    """
    match = PROJECTS_TABLE_RE.search(text)
    if not match:
        return text, 0

    header = match.group(1)
    sep = match.group(2)
    body = match.group(3)

    existing_rows: dict[str, str] = {}
    if merge_existing and body.strip():
        for line in body.splitlines():
            if not line.startswith("|"):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts and parts[0] != "Project":
                existing_rows[parts[0]] = line

    for slug, item in projects.items():
        existing_rows[slug] = format_project_row(item)

    new_body = "".join(f"{line}\n" for line in existing_rows.values())
    replacement = header + sep + new_body
    new_text = text[: match.start()] + replacement + text[match.end() :]

    if "_Last updated:" in new_text:
        stamp = now_iso()
        new_text = re.sub(
            r"^_Last updated:\s*.+$",
            f"_Last updated: {stamp}_",
            new_text,
            count=1,
            flags=re.M,
        )
    return new_text, len(projects)


def bootstrap_global_context(
    memory_home: Path,
    manifest: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    gc_path = memory_home / "context" / "GLOBAL_CONTEXT.md"
    if not gc_path.is_file():
        return {"status": "skipped", "reason": "no_global_context", "projects": 0}

    projects = collect_projects_from_manifest(manifest)
    text = gc_path.read_text(encoding="utf-8")
    new_text, count = merge_projects_table(text, projects)
    result = {
        "status": "ok",
        "projects": len(projects),
        "rows_updated": count,
        "path": str(gc_path),
        "dry_run": dry_run,
    }
    if not dry_run and count > 0 and new_text != text:
        gc_path.write_text(new_text, encoding="utf-8")
    return result
