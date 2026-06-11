"""Test helpers for agent-memory scripts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def load_script_module(module_name: str, filename: str):
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(mod)
    return mod


def minimal_hub(root: Path, *, projects: int = 2, with_fails: bool = True) -> None:
    """Populate a minimal valid memory hub for integration tests."""
    (root / "context").mkdir(parents=True)
    (root / "feedback").mkdir()
    (root / "chats" / "projects").mkdir(parents=True)

    projects_table = "\n".join(
        f"| app{i} | `~/app{i}` | active | distill |"
        for i in range(1, projects + 1)
    )
    gc = f"""# Global Context — Test
_Last updated: 2026-01-01_

## Me
- test user

## Projects
| Project | Path | Status | Details |
|---------|------|--------|---------|
{projects_table}
"""
    (root / "context" / "GLOBAL_CONTEXT.md").write_text(gc, encoding="utf-8")
    (root / "context" / "conventions.md").write_text(
        "# Conventions\n\n## Git\n\n- rule one\n- rule two\n",
        encoding="utf-8",
    )
    (root / "feedback" / "wins.md").write_text(
        "## 2026-01 Topic\n\n+ something worked\n",
        encoding="utf-8",
    )
    fails = (
        "## 2026-01 Closed\n\n"
        "- bad idea\n"
        "  _superseded → conventions.md § Git_\n\n"
        "## 2026-01 Open\n\n"
        "- still bad\n"
    )
    (root / "feedback" / "fails.md").write_text(
        fails if with_fails else "## 2026-01 Topic\n\n- only one\n",
        encoding="utf-8",
    )
    manifest = {
        "processed": [
            {
                "id": "abc-123",
                "distilled_at": "2026-01-01",
                "summary": "test",
            }
        ],
        "pending": [],
    }
    (root / "chats" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (root / "chats" / "projects" / "app1.md").write_text(
        "# app1\n\n## Summary\n\ntest\n", encoding="utf-8"
    )
