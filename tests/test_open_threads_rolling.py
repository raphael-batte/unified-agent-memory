"""Rolling 30d cross-hub Open threads aggregation (lib/open_threads.py)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.open_threads import collect_open_threads, threads_in_file  # noqa: E402

NOW = datetime(2026, 7, 12, 12, 0, 0)


def _project(hub: Path, slug: str, threads_block: str, last_updated: str = "2026-07-12") -> Path:
    path = hub / "chats" / "projects" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {slug}\n_Last updated: {last_updated}_\n\n"
        "## Decisions\n\n- keep\n\n"
        f"## Open threads\n\n{threads_block}\n\n"
        "## Recent\n\n- old\n",
        encoding="utf-8",
    )
    return path


class TestRollingOpenThreads(unittest.TestCase):
    def test_collect_union_across_project_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "alpha-hub", "- **[beta-seo]** defer head · _upd 2026-07-11_")
            _project(hub, "beta-app", "- **[admin]** paginator · _upd 2026-07-05_")
            got = collect_open_threads(hub, days=30, now=NOW)
            labels = {(t.slug, t.label) for t in got}
            # Cross-topic thread in alpha-hub.md is surfaced hub-wide
            self.assertIn(("alpha-hub", "beta-seo"), labels)
            self.assertIn(("beta-app", "admin"), labels)

    def test_workspace_slug_does_not_gate_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "alpha-hub", "- **[beta-seo]** defer head · _upd 2026-07-11_")
            # Asking from beta-app workspace still sees the alpha-hub thread
            got = collect_open_threads(hub, days=30, now=NOW, priority_slug="beta-app")
            self.assertTrue(any(t.label == "beta-seo" for t in got))

    def test_priority_slug_sorts_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "alpha-hub", "- **[a]** newer · _upd 2026-07-11_")
            _project(hub, "beta-app", "- **[b]** older · _upd 2026-07-01_")
            got = collect_open_threads(hub, days=30, now=NOW, priority_slug="beta-app")
            self.assertEqual(got[0].slug, "beta-app")

    def test_auto_drafts_capped_per_project_and_by_age(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(
                hub,
                "alpha-hub",
                "- **[billing]** keep invoices in sync · _upd 2026-06-20_\n"
                "- **[x]** [auto] newest draft · _upd 2026-07-11_\n"
                "- **[y]** [auto] older draft · _upd 2026-07-08_",
            )
            _project(hub, "beta-app", "- **[z]** [auto] stale draft · _upd 2026-06-25_")
            got = {(t.slug, t.label) for t in collect_open_threads(hub, days=30, now=NOW)}
            # curated stays for the full window; one fresh draft per project
            self.assertEqual(got, {("alpha-hub", "billing"), ("alpha-hub", "x")})
            everything = collect_open_threads(
                hub, days=30, now=NOW, auto_days=0, auto_per_project=0
            )
            self.assertEqual(len(everything), 4)

    def test_filter_evicts_older_than_30d(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(
                hub,
                "app",
                "- **[fresh]** t · _upd 2026-06-20_\n- **[stale]** t · _upd 2026-05-01_",
            )
            got = collect_open_threads(hub, days=30, now=NOW)
            labels = [t.label for t in got]
            self.assertIn("fresh", labels)  # 22 days
            self.assertNotIn("stale", labels)  # ~72 days

    def test_same_label_different_slug_not_merged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "a", "- **[admin]** aaa · _upd 2026-07-10_")
            _project(hub, "b", "- **[admin]** bbb · _upd 2026-07-10_")
            got = collect_open_threads(hub, days=30, now=NOW)
            keys = {(t.slug, t.label) for t in got}
            self.assertEqual(keys, {("a", "admin"), ("b", "admin")})

    def test_undated_bullet_falls_back_to_file_last_updated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "app", "- **[legacy]** no stamp", last_updated="2026-07-10")
            got = threads_in_file(hub / "chats" / "projects" / "app.md")
            self.assertEqual(got[0].updated, "2026-07-10")

    def test_example_project_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "example", "- **[demo]** t · _upd 2026-07-11_")
            got = collect_open_threads(hub, days=30, now=NOW)
            self.assertEqual(got, [])


class TestRoutingHintThreads(unittest.TestCase):
    def _load_routing_hint(self):
        path = SCRIPTS / "memory-routing-hint.py"
        spec = importlib.util.spec_from_file_location("routing_hint_mod", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_routing_hint_returns_active_threads_json(self) -> None:
        import io
        import contextlib
        import json

        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _project(hub, "alpha-hub", "- **[seo]** defer head · _upd 2026-07-11_")
            mod = self._load_routing_hint()
            argv = ["prog", str(hub), "--memory-home", str(hub), "--days", "100000", "--json"]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                old = sys.argv
                sys.argv = argv
                try:
                    mod.main()
                finally:
                    sys.argv = old
            payload = json.loads(buf.getvalue())
            self.assertIn("open_threads", payload)
            self.assertTrue(any(t["label"] == "seo" for t in payload["open_threads"]))


if __name__ == "__main__":
    unittest.main()
