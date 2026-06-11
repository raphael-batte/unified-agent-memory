"""Tests for scripts/lib/migrate_hub.py and migrate-memory restore paths."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO = SCRIPTS.parent
TEMPLATES = REPO / "templates"
sys.path.insert(0, str(SCRIPTS))

from lib import chats_manifest as cm  # noqa: E402
from lib.migrate_hub import migrate_hub  # noqa: E402


def _seed_old_hub(root: Path, *, n_manifest: int = 3) -> None:
    (root / "context").mkdir(parents=True)
    (root / "feedback").mkdir()
    (root / "chats" / "projects").mkdir(parents=True)
    (root / "chats" / "extracts").mkdir(parents=True)

    (root / "context" / "GLOBAL_CONTEXT.md").write_text(
        "# Global Context — Restored\n\n## Me\n- restored user\n\n## Projects\n| x | y | z | a |\n",
        encoding="utf-8",
    )
    (root / "feedback" / "wins.md").write_text(
        "## Topic\n\n+ restored win\n",
        encoding="utf-8",
    )
    processed = [
        {
            "id": f"chat-{i:03d}",
            "distilled_at": f"2026-06-0{i}",
            "summary": f"summary {i}",
            "distilled_to": ["projects/app.md"],
        }
        for i in range(1, n_manifest + 1)
    ]
    (root / "chats" / "manifest.json").write_text(
        json.dumps({"processed": processed, "pending": []}),
        encoding="utf-8",
    )
    (root / "chats" / "projects" / "app.md").write_text(
        "# app\n\n## Recent\n\n- distilled [title](chat-001)\n",
        encoding="utf-8",
    )
    (root / "config.json").write_text(
        json.dumps({"memory_home": str(root)}),
        encoding="utf-8",
    )


def _init_fresh_hub(dest: Path) -> None:
    """Simulate sessionStart init-memory on empty hub."""
    proc = subprocess.run(
        ["bash", str(REPO / "scripts" / "init-memory.sh")],
        env={"MEMORY_HOME": str(dest), "HOME": str(Path.home())},
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)


class TestMigrateHub(unittest.TestCase):
    def test_merge_manifest_after_init_beats_empty_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            new = Path(tmp) / "new"
            _seed_old_hub(old, n_manifest=5)
            _init_fresh_hub(new)

            dest_manifest = cm.load_manifest(new / "chats" / "manifest.json")
            self.assertEqual(len(dest_manifest.get("processed") or []), 0)

            report = migrate_hub(old, new, template_root=TEMPLATES, mode="merge")
            self.assertTrue(report.ok, report.errors)

            merged = cm.load_manifest(new / "chats" / "manifest.json")
            self.assertEqual(len(merged.get("processed") or []), 5)
            self.assertIn("restored user", (new / "context" / "GLOBAL_CONTEXT.md").read_text())

    def test_merge_keeps_user_edited_dest_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            new = Path(tmp) / "new"
            _seed_old_hub(old, n_manifest=1)
            _init_fresh_hub(new)
            edited = "# Global Context — User edited\n\n## Me\n- keep me\n"
            (new / "context" / "GLOBAL_CONTEXT.md").write_text(edited, encoding="utf-8")

            report = migrate_hub(old, new, template_root=TEMPLATES, mode="merge")
            self.assertTrue(report.ok)
            self.assertEqual((new / "context" / "GLOBAL_CONTEXT.md").read_text(), edited)
            self.assertTrue(any("skipped user-edited" in w for w in report.warnings))

    def test_overwrite_replaces_user_edited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            new = Path(tmp) / "new"
            _seed_old_hub(old, n_manifest=2)
            _init_fresh_hub(new)
            (new / "context" / "GLOBAL_CONTEXT.md").write_text("user", encoding="utf-8")

            report = migrate_hub(old, new, template_root=TEMPLATES, mode="overwrite")
            self.assertTrue(report.ok)
            self.assertIn("restored user", (new / "context" / "GLOBAL_CONTEXT.md").read_text())

    def test_ignore_existing_leaves_empty_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            new = Path(tmp) / "new"
            _seed_old_hub(old, n_manifest=4)
            _init_fresh_hub(new)

            report = migrate_hub(old, new, template_root=TEMPLATES, mode="ignore-existing")
            self.assertFalse(report.ok)
            merged = cm.load_manifest(new / "chats" / "manifest.json")
            self.assertEqual(len(merged.get("processed") or []), 0)

    def test_rebuild_manifest_from_extracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "chats" / "extracts").mkdir(parents=True)
            (hub / "chats" / "projects").mkdir(parents=True)
            (hub / "chats" / "manifest.json").write_text(
                '{"processed":[],"pending":[]}', encoding="utf-8"
            )
            (hub / "chats" / "extracts" / "abc.json").write_text(
                json.dumps(
                    {
                        "uuid": "abc-1111-2222-3333-444455556666",
                        "workspace": "Users-x-Work-Foo",
                        "workspace_slug": "Foo",
                        "date": "2026-06-01",
                        "first_query": "hello",
                    }
                ),
                encoding="utf-8",
            )
            manifest, stats = cm.rebuild_manifest_from_hub(hub)
            self.assertEqual(stats["from_extracts"], 1)
            self.assertEqual(len(cm.processed_by_id(manifest)), 1)


class TestChatsManifestMerge(unittest.TestCase):
    def test_merge_manifests_picks_newer(self) -> None:
        source = {
            "processed": [
                {
                    "id": "a",
                    "distilled_at": "2026-06-08",
                    "summary": "newer",
                }
            ]
        }
        dest = {
            "processed": [
                {
                    "id": "a",
                    "distilled_at": "2026-06-01",
                    "summary": "older",
                },
                {"id": "b", "distilled_at": "2026-06-02", "summary": "only dest"},
            ]
        }
        merged, stats = cm.merge_manifests(source, dest)
        by_id = cm.processed_by_id(merged)
        self.assertEqual(by_id["a"]["summary"], "newer")
        self.assertEqual(by_id["b"]["summary"], "only dest")
        self.assertEqual(stats["merged_total"], 2)
        self.assertEqual(stats["updated"], 1)


if __name__ == "__main__":
    unittest.main()
