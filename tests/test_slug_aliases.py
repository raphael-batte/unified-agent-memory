"""Tests for scripts/lib/slug_aliases.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.slug_aliases import apply_merges, canonical_slug, plan_merges  # noqa: E402
from lib.workspace_slug_resolve import resolve_slug  # noqa: E402


def _hub(root: Path, aliases: dict) -> Path:
    hub = root / "hub"
    (hub / "chats" / "projects").mkdir(parents=True)
    (hub / "chats" / "archive").mkdir()
    (hub / ".state").mkdir()
    (hub / "config.json").write_text(json.dumps({"slug_aliases": aliases}), encoding="utf-8")
    return hub


def _project(hub: Path, slug: str, decisions: list[str], threads: list[str], recent: list[str]) -> None:
    def block(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items)

    (hub / "chats" / "projects" / f"{slug}.md").write_text(
        f"# {slug}\n_Last updated: 2026-07-12_\n\n## Summary\n\n- about {slug}\n\n"
        f"## Decisions\n\n{block(decisions)}\n\n## Open threads\n\n{block(threads)}\n\n"
        f"## Recent\n\n{block(recent)}\n",
        encoding="utf-8",
    )


class TestCanonicalSlug(unittest.TestCase):
    def test_follows_chain_and_stops_on_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp), {"beta_app": "beta-app-old", "beta-app-old": "beta-app", "x": "y", "y": "x"})
            self.assertEqual(canonical_slug("Beta_App", hub), "beta-app")
            self.assertIn(canonical_slug("x", hub), {"x", "y"})
            self.assertEqual(canonical_slug("alpha-hub", hub), "alpha-hub")

    def test_routing_resolves_alias_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp), {"beta_app": "beta-app"})
            _project(hub, "beta-app", [], [], [])
            _project(hub, "beta_app", [], [], [])
            slug, reason = resolve_slug(Path(tmp) / "beta_app", memory_home=hub)
            self.assertEqual((slug, reason), ("beta-app", "alias"))


class TestMerge(unittest.TestCase):
    def test_merge_unions_sections_and_rewrites_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp), {"beta_app": "beta-app"})
            _project(hub, "beta-app", ["use the paginator"], ["**[ui]** header · _upd 2026-07-10_"], ["2026-07-10: new"])
            _project(hub, "beta_app", ["use the paginator", "cache the feed"], [], ["2026-06-01: old"])
            (hub / "chats" / "archive" / "beta_app-decisions.md").write_text(
                "# beta_app\n\n- [extracted] evicted one\n", encoding="utf-8"
            )
            (hub / "chats" / "manifest.json").write_text(json.dumps({"processed": [
                {"id": "c1", "distilled_to": ["projects/beta_app.md"]},
                {"id": "c2", "distilled_to": ["projects/beta_app.md", "projects/beta-app.md"]},
            ], "pending": []}), encoding="utf-8")
            (hub / ".state" / "pointer-curation-queue.json").write_text(json.dumps([
                {"kind": "open-thread", "project_rel": "projects/beta_app.md", "workspace_slug": "beta_app"},
            ]), encoding="utf-8")

            plans = plan_merges(hub)
            self.assertEqual([(p.src, p.dst) for p in plans], [("beta_app", "beta-app")])
            self.assertEqual(plans[0].added, {"Decisions": 1, "Recent": 1})
            self.assertEqual((plans[0].manifest_rows, plans[0].queue_rows), (2, 1))

            result = apply_merges(hub, plans)
            text = (hub / "chats" / "projects" / "beta-app.md").read_text(encoding="utf-8")
            self.assertEqual(text.count("use the paginator"), 1)
            self.assertIn("cache the feed", text)
            self.assertIn("2026-06-01: old", text)
            self.assertIn("about beta-app", text)
            self.assertFalse((hub / "chats" / "projects" / "beta_app.md").exists())
            self.assertIn(
                "evicted one",
                (hub / "chats" / "archive" / "beta-app-decisions.md").read_text(encoding="utf-8"),
            )
            manifest = json.loads((hub / "chats" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [e["distilled_to"] for e in manifest["processed"]],
                [["projects/beta-app.md"], ["projects/beta-app.md"]],
            )
            queue = json.loads((hub / ".state" / "pointer-curation-queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue[0]["project_rel"], "projects/beta-app.md")
            backup = Path(result["backup"])
            self.assertTrue((backup / "projects" / "beta_app.md").is_file())
            self.assertTrue((backup / "manifest.json").is_file())
            self.assertEqual(plan_merges(hub), [])

    def test_alias_without_target_file_is_a_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp), {"beta_app": "beta-app"})
            _project(hub, "beta_app", ["keep this"], [], [])
            apply_merges(hub, plan_merges(hub))
            text = (hub / "chats" / "projects" / "beta-app.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# beta-app\n"))
            self.assertIn("keep this", text)


if __name__ == "__main__":
    unittest.main()
