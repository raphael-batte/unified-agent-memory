"""Parse hub markdown into sections and bullets (shared by merge + search)."""

from __future__ import annotations

import re

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
_LAST_UPDATED = re.compile(r"^_Last updated:\s*(.+)$", re.M | re.I)
_CHAT_LINK_RE = re.compile(r"\]\(([0-9a-f-]{8,})\)", re.I)


def parse_sections(text: str) -> tuple[str, dict[str, str]]:
    preamble_lines: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            current = m.group(1).strip()
            sections[current] = []
            continue
        if current is None:
            preamble_lines.append(line)
        else:
            sections[current].append(line)

    preamble = "\n".join(preamble_lines).strip()
    return preamble, {k: "\n".join(v).strip() for k, v in sections.items()}


def bullets(block: str) -> list[str]:
    out: list[str] = []
    for line in block.splitlines():
        m = _BULLET_RE.match(line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def paragraph_units(block: str, *, max_len: int = 400) -> list[str]:
    """Non-bullet text chunks (paragraphs, table rows) for context files."""
    units: list[str] = []
    buf: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if buf:
                text = " ".join(buf).strip()
                if text:
                    units.append(text[:max_len])
                buf = []
            continue
        if _BULLET_RE.match(stripped):
            continue
        if _TABLE_ROW_RE.match(stripped) and "---" not in stripped:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            row = " | ".join(c for c in cells if c)
            if row and "Project" not in row:
                units.append(row[:max_len])
            continue
        buf.append(stripped)
    if buf:
        text = " ".join(buf).strip()
        if text:
            units.append(text[:max_len])
    return units


def last_updated_from_preamble(preamble: str) -> str | None:
    m = _LAST_UPDATED.search(preamble)
    if not m:
        return None
    return m.group(1).strip()[:10]


def chat_id_from_bullet(bullet: str) -> str | None:
    m = _CHAT_LINK_RE.search(bullet)
    return m.group(1) if m else None
