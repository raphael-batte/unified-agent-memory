"""Apply distill extract into chats/projects/<slug>.md (preserve language)."""

from __future__ import annotations

import re
from pathlib import Path

from lib.defaults import (
    DEFAULT_KEYWORDS,
    MAX_DECISIONS_ADD_PER_DISTILL,
    MAX_EXTRACTED_DECISIONS_PER_FILE,
    MAX_LAYER_FILE_LINES,
)
from lib.transcript_cursor import safe_path_component
from lib.distill_links import enrich_extract, format_chat_markdown_link, recent_bullet
from lib.forward_pointer import (
    NO_POINTER_MARKER,
    STALE_POINTER_PREFIX,
    extract_forward_pointer_result,
)
from lib.message_importance import mechanical_bullets
from lib.novelty import is_novel, normalize_snippet
from lib.secrets_guard import scan_file
from lib.pointer_metrics import maybe_log_pointer_clobbered
from lib.pointer_provenance import (
    PROVENANCE_AUTO,
    PROVENANCE_CURATED,
    find_curated_next_step,
    format_curated_next_step,
    is_strong_pointer_source,
    pointer_provenance_class,
    watermark_changed,
)
from lib.markdown_sections import bullets as _bullets
from lib.markdown_sections import parse_sections as _parse_sections
from lib.timestamps import now_iso

LAST_UPDATED = re.compile(r"^_Last updated:\s*.+$", re.M | re.I)
DEFAULT_SECTIONS = (
    "Summary",
    "Decisions",
    "Next step",
    "Preferences",
    "Open threads",
    "Recent",
)


def _today() -> str:
    return now_iso()


def _join_sections(preamble: str, sections: dict[str, str]) -> str:
    lines: list[str] = []
    if preamble:
        lines.append(preamble)
        lines.append("")
    for name in DEFAULT_SECTIONS:
        if name not in sections:
            continue
        lines.append(f"## {name}")
        lines.append("")
        body = sections[name].strip()
        if body:
            lines.append(body)
        lines.append("")
    for name, body in sections.items():
        if name in DEFAULT_SECTIONS:
            continue
        lines.append(f"## {name}")
        lines.append("")
        if body.strip():
            lines.append(body.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def recent_line(extract: dict, today: str | None = None) -> str:
    return recent_bullet(extract, today or _today())


def _is_meta_next_step(bullet: str) -> bool:
    return NO_POINTER_MARKER in bullet or bullet.strip().startswith(STALE_POINTER_PREFIX)


def _previous_real_next_step(bullets: list[str]) -> str | None:
    for bullet in bullets:
        if _is_meta_next_step(bullet):
            continue
        text = bullet.strip()
        if text:
            return text
    return None


def format_next_step_line(
    extract: dict,
    pointer: str | None,
    existing_block: str,
) -> tuple[str, str]:
    """
    Build ## Next step body (single bullet).
    Returns (section_body, kind) where kind is extracted | placeholder_empty | placeholder_stale.
    """
    link = format_chat_markdown_link(enrich_extract(extract))
    if link:
        drill = (
            f" Drill → {link} (transcript tail). "
            "Context → ## Decisions, ## Recent below."
        )
    else:
        uid = str(extract.get("uuid", "?"))[:8]
        drill = (
            f" Drill → chat `{uid}…` in ## Recent. "
            "Context → ## Decisions below."
        )

    if pointer:
        return f"- {pointer}", "extracted"

    prev = _previous_real_next_step(_bullets(existing_block))
    if prev:
        short = prev if len(prev) <= 120 else prev[:117].rstrip() + "..."
        return (
            f"- {STALE_POINTER_PREFIX} _Not refreshed._ Was: «{short}».{drill}",
            "placeholder_stale",
        )
    return f"- {NO_POINTER_MARKER}{drill}", "placeholder_empty"


def decision_candidates_from_extract(
    extract: dict,
    *,
    max_items: int = 3,
    max_len: int = 200,
    min_len: int = 24,
) -> list[str]:
    """
    Decision seeds from extract — prefer cue-based decision_candidates, else keywords.
    Used only when Decisions is empty — agent should refine later.
    """
    structured = extract.get("decision_candidates") or []
    if structured:
        out: list[str] = []
        for row in structured[:max_items]:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if len(text) < min_len:
                continue
            if len(text) > max_len:
                text = text[: max_len - 3].rstrip() + "..."
            out.append(f"[extracted] {text}")
        if out:
            return out

    seen: set[str] = set()
    out = []
    for msg in extract.get("user_messages") or []:
        text = re.sub(r"\s+", " ", msg.strip())
        if len(text) < min_len:
            continue
        lower = text.lower()
        if not any(kw in lower for kw in DEFAULT_KEYWORDS):
            continue
        if len(text) > max_len:
            text = text[: max_len - 3].rstrip() + "..."
        if text in seen:
            continue
        seen.add(text)
        out.append(f"[bootstrap] {text}")
        if len(out) >= max_items:
            break
    return out


def _is_extracted_decision(bullet: str) -> bool:
    return bullet.strip().startswith("[extracted]")


def archive_evicted_decisions(
    memory_home: Path | None,
    slug: str,
    bullets: list[str],
) -> int:
    """Append evicted [extracted] bullets to chats/archive/<slug>-decisions.md."""
    if memory_home is None or not bullets:
        return 0
    safe = safe_path_component(slug or "project")
    path = memory_home / "chats" / "archive" / f"{safe}-decisions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    day = _today()
    lines = [b if b.strip().startswith("- ") else f"- {b}" for b in bullets]
    block = "\n".join(lines)
    if path.is_file():
        prev = path.read_text(encoding="utf-8", errors="replace").rstrip()
        path.write_text(
            prev + f"\n\n<!-- evicted {day} -->\n{block}\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            f"# Archived decisions — {slug}\n\n{block}\n",
            encoding="utf-8",
        )
    return len(bullets)


def enforce_extracted_decisions_cap(
    bullets: list[str],
    *,
    max_extracted: int,
    memory_home: Path | None = None,
    slug: str = "project",
) -> tuple[list[str], int]:
    """
    Keep curated/mechanical bullets; cap [extracted] count (FIFO evict oldest).
    Returns (trimmed_bullets, evicted_count).
    """
    if max_extracted <= 0:
        return bullets, 0
    curated: list[str] = []
    extracted: list[str] = []
    for bullet in bullets:
        if _is_extracted_decision(bullet):
            extracted.append(bullet)
        else:
            curated.append(bullet)
    if len(extracted) <= max_extracted:
        return curated + extracted, 0
    evicted = extracted[: len(extracted) - max_extracted]
    kept = extracted[len(extracted) - max_extracted :]
    archive_evicted_decisions(memory_home, slug, evicted)
    return curated + kept, len(evicted)


def merge_extracted_decisions(
    existing: list[str],
    extract: dict,
    *,
    max_add: int = MAX_DECISIONS_ADD_PER_DISTILL,
    max_extracted: int = MAX_EXTRACTED_DECISIONS_PER_FILE,
    memory_home: Path | None = None,
    slug: str | None = None,
) -> tuple[list[str], int]:
    """Append novel [extracted] decisions; never remove curated bullets."""
    slug = slug or str(extract.get("workspace_slug") or "project")
    existing, _evicted = enforce_extracted_decisions_cap(
        existing,
        max_extracted=max_extracted,
        memory_home=memory_home,
        slug=slug,
    )
    candidates = extract.get("decision_candidates") or []
    if not candidates:
        return existing, 0
    prior = [normalize_snippet(b) for b in existing if b.strip()]
    out = list(existing)
    added = 0
    for row in candidates:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        line = f"[extracted] {text}"
        if not is_novel(text, prior):
            continue
        out.append(line)
        prior.append(normalize_snippet(text))
        added += 1
        if added >= max_add:
            break
    out, _ = enforce_extracted_decisions_cap(
        out,
        max_extracted=max_extracted,
        memory_home=memory_home,
        slug=slug,
    )
    return out, added


def apply_mechanical_auto_decisions(project_path: Path, extract: dict) -> int:
    """Graceful first-run fallback — keyword-free [auto] Decisions bullets."""
    bullets = mechanical_bullets(extract.get("user_messages") or [], max_items=3)
    if not bullets:
        return 0
    seeds = [f"[auto] {b}" for b in bullets]
    project_path.parent.mkdir(parents=True, exist_ok=True)
    day = _today()
    if project_path.is_file():
        text = project_path.read_text(encoding="utf-8", errors="replace")
    else:
        slug = extract.get("workspace_slug", "project")
        text = (
            f"# {slug}\n"
            f"_Last updated: {day}_\n\n"
            "## Summary\n\n\n"
            "## Decisions\n\n\n"
            "## Next step\n\n\n"
            "## Preferences\n\n\n"
            "## Open threads\n\n\n"
            "## Recent\n\n"
        )
    preamble, sections = _parse_sections(text)
    if _bullets(sections.get("Decisions", "")):
        return 0
    sections["Decisions"] = _format_bullets(seeds)
    project_path.write_text(_join_sections(preamble, sections), encoding="utf-8")
    return len(seeds)


def apply_extract_to_project(
    project_path: Path,
    extract: dict,
    *,
    max_recent: int = 3,
    today: str | None = None,
    bootstrap_decisions: bool = False,
    memory_home: Path | None = None,
    manifest_entry: dict | None = None,
) -> dict:
    """
    Bookkeeping merge: _Last updated_ + Recent≤3.
    Optional bootstrap_decisions when ## Decisions is empty (first sync).
    Does NOT write Summary — agent curates from staging.
    Raises ValueError if merged text fails secrets scan.
    """
    day = today or _today()
    project_path.parent.mkdir(parents=True, exist_ok=True)

    if project_path.is_file():
        text = project_path.read_text(encoding="utf-8", errors="replace")
    else:
        slug = extract.get("workspace_slug", "project")
        text = (
            f"# {slug}\n"
            f"_Last updated: {day}_\n\n"
            "## Summary\n\n\n"
            "## Decisions\n\n\n"
            "## Next step\n\n\n"
            "## Preferences\n\n\n"
            "## Open threads\n\n\n"
            "## Recent\n\n"
        )

    if LAST_UPDATED.search(text):
        text = LAST_UPDATED.sub(f"_Last updated: {day}_", text, count=1)
    else:
        lines = text.splitlines()
        if lines:
            lines.insert(1, f"_Last updated: {day}_")
            text = "\n".join(lines) + "\n"

    preamble, sections = _parse_sections(text)

    summary_bullets = extract.get("summary_bullets") or []
    if summary_bullets and not _bullets(sections.get("Summary", "")):
        clean = [str(b).strip() for b in summary_bullets if str(b).strip()]
        if clean:
            sections["Summary"] = _format_bullets(clean[:5])

    existing_decisions = _bullets(sections.get("Decisions", ""))
    from lib.memory_config import load_hub_config  # noqa: E402
    from lib.defaults import load_thresholds  # noqa: E402

    thresholds = load_thresholds(
        load_hub_config(memory_home) if memory_home is not None else None
    )
    max_extracted = int(thresholds["max_extracted_decisions_per_file"])
    max_add = int(thresholds["max_decisions_add_per_distill"])
    slug = str(extract.get("workspace_slug") or project_path.stem)
    merged_decisions, decisions_merged = merge_extracted_decisions(
        existing_decisions,
        extract,
        max_add=max_add,
        max_extracted=max_extracted,
        memory_home=memory_home,
        slug=slug,
    )
    if merged_decisions != existing_decisions:
        sections["Decisions"] = _format_bullets(merged_decisions)

    existing_recent = _bullets(sections.get("Recent", ""))
    new_recent_line = recent_line(extract, day)
    recent_items = [new_recent_line] + [r for r in existing_recent if r != new_recent_line]
    sections["Recent"] = _format_bullets(recent_items[:max_recent])

    decisions_added = 0
    if bootstrap_decisions and not _bullets(sections.get("Decisions", "")):
        seeds = decision_candidates_from_extract(extract)
        if seeds:
            sections["Decisions"] = _format_bullets(seeds)
            decisions_added = len(seeds)

    existing_next_bullets = _bullets(sections.get("Next step", ""))
    curated_text = find_curated_next_step(existing_next_bullets)
    prev_next_step = _previous_real_next_step(existing_next_bullets)
    pointer_result = extract_forward_pointer_result(extract, memory_home=memory_home)
    pointer_candidate = pointer_result.text
    pointer_preserved_curated = False
    pointer_provenance = PROVENANCE_AUTO

    if curated_text:
        strong = is_strong_pointer_source(pointer_result.source)
        wm_changed = watermark_changed(extract, manifest_entry)
        if strong and wm_changed and pointer_candidate:
            next_body, next_kind = format_next_step_line(
                extract, pointer_candidate, sections.get("Next step", "")
            )
            pointer_provenance = pointer_provenance_class(pointer_result.source)
        else:
            next_body = sections.get("Next step", "").strip()
            if not next_body:
                next_body = format_curated_next_step(curated_text)
            next_kind = "curated_preserved"
            pointer_preserved_curated = True
            pointer_provenance = PROVENANCE_CURATED
    else:
        next_body, next_kind = format_next_step_line(
            extract, pointer_candidate, sections.get("Next step", "")
        )
        if next_kind == "extracted":
            pointer_provenance = pointer_provenance_class(pointer_result.source)

    maybe_log_pointer_clobbered(
        memory_home,
        workspace_slug=str(extract.get("workspace_slug") or project_path.stem),
        new_chat_id=str(extract.get("uuid") or ""),
        existing_recent=existing_recent,
        prev_next_step=prev_next_step,
        next_kind=next_kind,
    )
    sections["Next step"] = next_body
    next_step_updated = next_kind != "curated_preserved"
    next_step_placeholder = next_kind not in ("extracted", "curated_preserved")

    merged = _join_sections(preamble, sections)

    tmp = project_path.with_suffix(".md.tmpcheck")
    tmp.write_text(merged, encoding="utf-8")
    try:
        hits = scan_file(tmp)
        if hits:
            raise ValueError(
                f"refusing to write project file — secrets detected: {hits[0]}"
            )
    finally:
        tmp.unlink(missing_ok=True)

    project_path.write_text(merged, encoding="utf-8")

    return {
        "project_file": str(project_path),
        "decisions_added": decisions_added,
        "decisions_merged": decisions_merged,
        "decisions_extracted": int(extract.get("decisions_extracted") or 0),
        "coverage_ratio": extract.get("coverage_ratio"),
        "next_step_updated": next_step_updated,
        "next_step_kind": next_kind,
        "next_step_placeholder": next_step_placeholder,
        "pointer_confidence": pointer_result.confidence,
        "pointer_source": pointer_result.source,
        "pointer_provenance": pointer_provenance,
        "pointer_preserved_curated": pointer_preserved_curated,
        "pointer_candidate": pointer_candidate if pointer_preserved_curated else None,
        "recent_lines": min(len(recent_items), max_recent),
        "lines": len(merged.splitlines()),
        "over_limit": len(merged.splitlines()) > MAX_LAYER_FILE_LINES,
    }
