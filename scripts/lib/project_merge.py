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
from lib.distill_links import recent_bullet
from lib.hub_lock import write_atomic
from lib.message_importance import mechanical_bullets
from lib.novelty import (
    dedupe_bullets,
    dedupe_decision_bullets,
    is_decision_junk,
    is_novel,
    normalize_decision_content,
)
from lib.secrets_guard import scan_file
from lib.markdown_sections import bullets as _bullets
from lib.markdown_sections import format_bullets as _render_bullets
from lib.markdown_sections import parse_sections as _parse_sections
from lib.timestamps import now_iso

LAST_UPDATED = re.compile(r"^_Last updated:\s*.+$", re.M | re.I)
DEFAULT_SECTIONS = (
    "Summary",
    "Decisions",
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
    return _render_bullets(items)


def recent_line(extract: dict, today: str | None = None) -> str:
    return recent_bullet(extract, today or _today())


OPEN_THREAD_LABEL = re.compile(r"^\*\*\[(?P<label>[^\]]+)\]\*\*\s*(?P<text>.*)$", re.S)
# Trailing "· _upd YYYY-MM-DD_" tail-of-topic timestamp; tolerant of ISO too.
OPEN_THREAD_STAMP = re.compile(r"\s*·\s*_upd\s+(?P<date>[0-9T:\-]+)_\s*$")
OPEN_THREAD_AUTO_PREFIX = re.compile(r"^\[auto\]\s*", re.I)
MAX_OPEN_THREADS = 7
TIER_AUTO = "auto"
TIER_CURATED = "curated"


def open_thread_label(bullet: str) -> str | None:
    """Extract the ``[label]`` from a ``**[label]** …`` Open threads bullet."""
    m = OPEN_THREAD_LABEL.match(bullet.strip())
    return m.group("label").strip() if m else None


def _strip_stamp(text: str) -> tuple[str, str | None]:
    """Split trailing ``· _upd DATE_`` off a thread text. Returns (text, date|None)."""
    m = OPEN_THREAD_STAMP.search(text)
    if not m:
        return text.strip(), None
    return text[: m.start()].strip(), m.group("date").strip()


def parse_open_thread(bullet: str) -> dict | None:
    """
    Parse a ``**[label]** text · _upd DATE_`` bullet.

    Returns ``{"label", "text", "updated"}`` where ``updated`` is the raw date
    string (or ``None`` when the bullet carries no stamp). Non-matching lines → None.
    """
    m = OPEN_THREAD_LABEL.match(bullet.strip())
    if not m:
        return None
    label = m.group("label").strip()
    body, stamp = _strip_stamp(m.group("text").strip())
    if not label:
        return None
    return {"label": label, "text": body, "updated": stamp}


def format_open_thread(label: str, text: str, updated: str) -> str:
    """Build a ``**[label]** text · _upd DATE_`` bullet (timestamp = tail of topic)."""
    return f"**[{label}]** {text} · _upd {updated}_"


def strip_open_thread_auto_marker(text: str) -> str:
    return OPEN_THREAD_AUTO_PREFIX.sub("", text.strip()).strip()


def open_thread_tier(bullet: str) -> str:
    """Return ``auto`` when body starts with ``[auto]``; else ``curated``."""
    parsed = parse_open_thread(bullet)
    if not parsed:
        return TIER_CURATED
    body = parsed["text"]
    if body.lower().startswith("[auto]"):
        return TIER_AUTO
    return TIER_CURATED


def format_open_thread_tiered(
    label: str,
    text: str,
    updated: str,
    *,
    tier: str = TIER_CURATED,
) -> str:
    body, _ = _strip_stamp(text.strip())
    body = strip_open_thread_auto_marker(body)
    if tier == TIER_AUTO:
        body = f"[auto] {body}" if body else "[auto]"
    if not body:
        raise ValueError("open thread text is empty")
    return format_open_thread(label, body, updated)


def _cap_open_threads_tiered(bullets: list[str], cap: int) -> list[str]:
    """Cap list: evict oldest ``[auto]`` first; only then oldest curated."""
    if cap <= 0 or len(bullets) <= cap:
        return bullets
    ordered = list(bullets)
    while len(ordered) > cap:
        evict_idx = next(
            (i for i, b in enumerate(ordered) if open_thread_tier(b) == TIER_AUTO),
            None,
        )
        if evict_idx is None:
            ordered.pop(0)
        else:
            ordered.pop(evict_idx)
    return ordered


def upsert_open_thread_tiered(
    existing: list[str],
    label: str,
    text: str,
    *,
    updated: str,
    tier: str = TIER_AUTO,
    cap: int = MAX_OPEN_THREADS,
) -> tuple[list[str], bool, str]:
    """
    Tier-aware upsert for Open threads.

    Returns ``(bullets, changed, skip_reason)``.
    ``[auto]`` never overwrites curated for the same label; curated cap blocks new auto.
    """
    label = label.strip()
    body, _ = _strip_stamp(text.strip())
    body = strip_open_thread_auto_marker(body)
    if not label:
        raise ValueError("open thread label is empty")
    if not body:
        raise ValueError("open thread text is empty")

    label_key = label.lower()
    had_auto = any(open_thread_tier(b) == TIER_AUTO for b in existing)
    for bullet in existing:
        existing_label = open_thread_label(bullet)
        if not existing_label or existing_label.lower() != label_key:
            continue
        if tier == TIER_AUTO and open_thread_tier(bullet) == TIER_CURATED:
            return existing, False, "skipped_curated"
        break

    new_bullet = format_open_thread_tiered(label, body, updated, tier=tier)
    kept: list[str] = []
    for bullet in existing:
        stripped = bullet.strip()
        if not stripped:
            continue
        existing_label = open_thread_label(stripped)
        if existing_label and existing_label.lower() == label_key:
            continue
        kept.append(stripped)

    if tier == TIER_AUTO and len(kept) + 1 > cap:
        kept = [b for b in kept if open_thread_tier(b) != TIER_AUTO]

    while tier == TIER_AUTO and len(kept) >= cap:
        auto_indices = [
            i for i, b in enumerate(kept) if open_thread_tier(b) == TIER_AUTO
        ]
        if auto_indices:
            kept.pop(auto_indices[0])
            continue
        if had_auto:
            kept.pop(0)
            break
        return existing, False, "skipped_cap_curated_full"

    kept.append(new_bullet)
    kept = _cap_open_threads_tiered(kept, cap)
    return kept, True, ""


def upsert_open_thread(
    existing: list[str],
    label: str,
    text: str,
    *,
    updated: str,
    cap: int = MAX_OPEN_THREADS,
) -> list[str]:
    """
    Upsert a direction bullet into Open threads, stamping ``· _upd {updated}_``.

    - Replaces the bullet whose ``[label]`` matches (case-insensitive), else appends;
      a replace refreshes the timestamp (tail-of-topic moves forward).
    - Preserves order of other bullets; updated/new entry moves to the end (most recent).
    - Drops empty/placeholder bullets; caps to the last ``cap`` entries.
    Never invents labels and never touches non-matching curated bullets' text.
    """
    label = label.strip()
    body, _existing_stamp = _strip_stamp(text.strip())
    if not label:
        raise ValueError("open thread label is empty")
    if not body:
        raise ValueError("open thread text is empty")
    new_bullet = format_open_thread(label, body, updated)

    kept: list[str] = []
    for bullet in existing:
        stripped = bullet.strip()
        if not stripped:
            continue
        existing_label = open_thread_label(stripped)
        if existing_label and existing_label.lower() == label.lower():
            continue  # replaced by new_bullet appended below
        kept.append(stripped)
    kept.append(new_bullet)

    if cap > 0 and len(kept) > cap:
        kept = kept[len(kept) - cap :]
    return kept


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


def _authored_text(block: str) -> str:
    """Section text minus generated metadata lines (``_Last updated: …_``)."""
    keep = [
        line
        for line in block.splitlines()
        if line.strip() and not LAST_UPDATED.match(line.strip())
    ]
    return "\n".join(keep).strip()


def _is_machine_decision(bullet: str) -> bool:
    text = bullet.strip()
    return text.startswith(("[extracted]", "[bootstrap]", "[auto]"))


def has_curated_decisions(existing: list[str]) -> bool:
    """True once an agent has written real Decisions into the file.

    Raw candidates are seeds for curation, not content. Appending them next to
    curated bullets is what silently refilled hub files with verbatim user
    quotes, so the mechanical path stops as soon as curation has happened.
    """
    return any(b.strip() and not _is_machine_decision(b) for b in existing)


_ARCHIVE_DECISIONS_HEADING = "## Decisions"


def _ensure_archive_decisions_section(text: str, *, slug: str) -> str:
    """Legacy archives: bullets under H1 only — wrap for hub_search parse_sections."""
    if _ARCHIVE_DECISIONS_HEADING in text:
        return text
    lines = text.splitlines()
    if not lines:
        return f"# Archived decisions — {slug}\n\n{_ARCHIVE_DECISIONS_HEADING}\n\n"
    out: list[str] = []
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith("#"):
        out.append(lines[i])
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    else:
        out.append(f"# Archived decisions — {slug}")
    out.append("")
    out.append(_ARCHIVE_DECISIONS_HEADING)
    out.append("")
    if i < len(lines):
        out.extend(lines[i:])
    return "\n".join(out).rstrip() + "\n"


def _archive_bullets_from_text(text: str, *, slug: str) -> list[str]:
    normalized = _ensure_archive_decisions_section(text.rstrip(), slug=slug)
    _preamble, sections = _parse_sections(normalized)
    return _bullets(sections.get("Decisions", ""))


def _write_archive_decisions(path: Path, slug: str, bullets: list[str]) -> None:
    lines = [b if b.strip().startswith("- ") else f"- {b}" for b in bullets]
    body = "\n".join(lines)
    write_atomic(
        path, f"# Archived decisions — {slug}\n\n{_ARCHIVE_DECISIONS_HEADING}\n\n{body}\n"
    )


def archive_evicted_decisions(
    memory_home: Path | None,
    slug: str,
    bullets: list[str],
) -> int:
    """Append novel evicted [extracted] bullets; compact duplicates in archive file."""
    if memory_home is None or not bullets:
        return 0
    safe = safe_path_component(slug or "project")
    path = memory_home / "chats" / "archive" / f"{safe}-decisions.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    formatted = [b if b.strip().startswith("- ") else f"- {b}" for b in bullets]
    existing: list[str] = []
    if path.is_file():
        existing = _archive_bullets_from_text(
            path.read_text(encoding="utf-8", errors="replace"),
            slug=slug,
        )

    existing_deduped = dedupe_bullets(existing)
    prior_norms = [normalize_decision_content(b) for b in existing_deduped]
    novel_lines: list[str] = []
    for line in formatted:
        text = line.lstrip("- ").strip()
        if not text or not is_novel(text, prior_norms):
            continue
        novel_lines.append(line)
        prior_norms.append(normalize_decision_content(text))

    merged = dedupe_bullets(existing_deduped + novel_lines)
    if path.is_file() and not novel_lines and len(merged) == len(existing):
        return 0

    _write_archive_decisions(path, slug, merged)
    return len(novel_lines)


def compact_archive_decisions(memory_home: Path, slug: str) -> int:
    """Rewrite archive file with deduplicated ## Decisions bullets. Returns removed count."""
    safe = safe_path_component(slug or "project")
    path = memory_home / "chats" / "archive" / f"{safe}-decisions.md"
    if not path.is_file():
        return 0
    existing = _archive_bullets_from_text(
        path.read_text(encoding="utf-8", errors="replace"),
        slug=slug,
    )
    merged = dedupe_bullets(existing)
    if len(merged) == len(existing):
        return 0
    _write_archive_decisions(path, slug, merged)
    return len(existing) - len(merged)


def compact_live_decisions(bullets: list[str]) -> tuple[list[str], int]:
    """Dedupe + junk-drop live ## Decisions bullets (tier-priority, marker-agnostic)."""
    before = len(bullets)
    compacted = dedupe_decision_bullets(bullets)
    return compacted, before - len(compacted)


def compact_live_decisions_file(project_path: Path) -> int:
    """Rewrite project distill Decisions section when compact removes duplicates."""
    if not project_path.is_file():
        return 0
    text = project_path.read_text(encoding="utf-8", errors="replace")
    preamble, sections = _parse_sections(text)
    existing = _bullets(sections.get("Decisions", ""))
    if not existing or has_curated_decisions(existing):
        # Compaction exists to dedupe machine bullets. A curated section may hold
        # ### sub-headings, which a bullets-only rewrite would drop.
        return 0
    compacted, removed = compact_live_decisions(existing)
    if removed <= 0:
        return 0
    sections["Decisions"] = _format_bullets(compacted)
    write_atomic(project_path, _join_sections(preamble, sections))
    return removed


def compact_all_live_decisions(memory_home: Path) -> dict[str, int]:
    """Compact every ``chats/projects/*.md`` (skips ``example.md``)."""
    projects = memory_home / "chats" / "projects"
    if not projects.is_dir():
        return {}
    removed_by_slug: dict[str, int] = {}
    for path in sorted(projects.glob("*.md")):
        if path.name == "example.md":
            continue
        count = compact_live_decisions_file(path)
        if count:
            removed_by_slug[path.stem] = count
    return removed_by_slug


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
    """Append novel [extracted] decisions; never remove or shadow curated bullets."""
    slug = slug or str(extract.get("workspace_slug") or "project")
    if has_curated_decisions(existing):
        return existing, 0
    existing, _evicted = enforce_extracted_decisions_cap(
        existing,
        max_extracted=max_extracted,
        memory_home=memory_home,
        slug=slug,
    )
    candidates = extract.get("decision_candidates") or []
    if not candidates:
        return existing, 0
    prior = [normalize_decision_content(b) for b in existing if b.strip()]
    out = list(existing)
    added = 0
    for row in candidates:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text or is_decision_junk(text):
            continue
        line = f"[extracted] {text}"
        if not is_novel(text, prior):
            continue
        out.append(line)
        prior.append(normalize_decision_content(text))
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
            "## Preferences\n\n\n"
            "## Open threads\n\n\n"
            "## Recent\n\n"
        )
    preamble, sections = _parse_sections(text)
    if _bullets(sections.get("Decisions", "")):
        return 0
    sections["Decisions"] = _format_bullets(seeds)
    write_atomic(project_path, _join_sections(preamble, sections))
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
    # Any prose counts as an authored Summary — not just bullets, or a curated
    # paragraph reads as "empty" and gets replaced by raw distill lines. The
    # _Last updated_ stamp lands here in files with no H1, so it is not content.
    if summary_bullets and not _authored_text(sections.get("Summary", "")):
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

    decisions_now = _bullets(sections.get("Decisions", ""))
    if has_curated_decisions(decisions_now):
        decisions_now = []
    compacted_decisions, decisions_compacted = compact_live_decisions(decisions_now)
    if decisions_compacted:
        sections["Decisions"] = _format_bullets(compacted_decisions)

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

    write_atomic(project_path, merged)

    return {
        "project_file": str(project_path),
        "decisions_added": decisions_added,
        "decisions_merged": decisions_merged,
        "decisions_compacted": decisions_compacted,
        "decisions_extracted": int(extract.get("decisions_extracted") or 0),
        "coverage_ratio": extract.get("coverage_ratio"),
        "recent_lines": min(len(recent_items), max_recent),
        "lines": len(merged.splitlines()),
        "over_limit": len(merged.splitlines()) > MAX_LAYER_FILE_LINES,
    }
