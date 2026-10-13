"""Resolve workspace path → agent-memory project distill slug."""

from __future__ import annotations

from pathlib import Path

from lib.transcript_cursor import safe_path_component, workspace_slug


def slug_candidates(workspace: Path) -> list[str]:
    name = workspace.name
    if not name:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        s = safe_path_component(raw, fallback="")
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    add(name)
    add(workspace_slug(f"Users-Work-{name}"))
    add(workspace_slug(f"Users-x-Work-{name}"))
    # Cursor folder id: Users-<user>-Work-<repo>
    parts = workspace.parts
    if len(parts) >= 2:
        encoded = "-".join(parts[1:] if parts[0] == "/" else parts)
        add(encoded)
        add(workspace_slug(encoded))
    return out


def resolve_slug(
    workspace: Path,
    *,
    memory_home: Path,
) -> tuple[str | None, str]:
    """Return (slug, reason). slug None if no distill match."""
    from lib.slug_aliases import canonical_slug

    projects = memory_home / "chats" / "projects"
    for cand in slug_candidates(workspace):
        canon = canonical_slug(cand, memory_home)
        if canon != cand and (projects / f"{canon}.md").is_file():
            return canon, "alias"
    return _resolve_slug(workspace, memory_home=memory_home)


def _resolve_slug(
    workspace: Path,
    *,
    memory_home: Path,
) -> tuple[str | None, str]:
    projects = memory_home / "chats" / "projects"
    if not projects.is_dir():
        return None, "no_projects_dir"

    for cand in slug_candidates(workspace):
        if (projects / f"{cand}.md").is_file():
            return cand, "distill_match"

    distills = sorted(projects.glob("*.md"))
    distills = [p for p in distills if p.name != "example.md"]
    if len(distills) == 1:
        return distills[0].stem, "only_distill"

    if distills:
        want = workspace.name.lower()
        for p in distills:
            if p.stem.lower() == want:
                return p.stem, "case_insensitive_basename"

    fallback = slug_candidates(workspace)
    if fallback:
        return fallback[0], "basename_fallback"
    return None, "unresolved"
