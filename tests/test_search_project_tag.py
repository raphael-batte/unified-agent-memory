"""Ranking eval for project-tag search (hole #3).

Guards against silent ranking regressions: each case asserts the expected doc
outranks a distractor. The headline case is the real failure — a Steaklovers SEO
thread physically stored in Trendymen.md must beat agent-memory noise on a
"steaklovers" query, because the topic lives in the **[label]**, not the filename.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.hub_search import search_hub, _slug_tokens, _label_tokens  # noqa: E402


def _write(hub: Path, rel: str, body: str) -> None:
    path = hub / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class TestTagTokenHelpers(unittest.TestCase):
    def test_slug_tokens_strip_decisions_suffix(self) -> None:
        self.assertEqual(_slug_tokens("chats/archive/steaklovers-dev-decisions.md"),
                         _slug_tokens("chats/projects/steaklovers-dev.md"))

    def test_label_tokens_from_open_thread(self) -> None:
        toks = _label_tokens("**[steaklovers-seo]** defer head · _upd 2026-07-11_")
        self.assertIn("stea", toks)  # prefix-keyed
        self.assertIn("seo", toks)


class TestProjectTagRanking(unittest.TestCase):
    def test_label_bridges_workspace_vs_topic(self) -> None:
        # THE case: Steaklovers SEO recorded under the Trendymen workspace file.
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _write(
                hub,
                "chats/projects/Trendymen.md",
                "_Last updated: 2026-07-11_\n\n"
                "## Open threads\n\n"
                "- **[steaklovers-seo]** defer head, alt, H2/H3 · _upd 2026-07-11_\n",
            )
            _write(
                hub,
                "chats/projects/agent-memory.md",
                "_Last updated: 2026-07-11_\n\n"
                "## Decisions\n\n- [curated] canonical head defer LCP cover tuning notes\n",
            )
            result = search_hub(hub, "steaklovers head defer", top=5, log_metrics=False)
            hits = result["hits"]
            self.assertTrue(hits, "no hits")
            self.assertIn("steaklovers-seo", hits[0]["text"],
                          msg=f"top hit was: {hits[0]['text']!r}")

    def test_slug_lifts_whole_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _write(
                hub,
                "chats/projects/steaklovers-dev.md",
                "_Last updated: 2026-07-10_\n\n"
                "## Decisions\n\n- [curated] paginator fix on admin pages\n",
            )
            _write(
                hub,
                "chats/projects/other.md",
                "_Last updated: 2026-07-10_\n\n"
                "## Decisions\n\n- [curated] paginator fix on admin pages elsewhere too\n",
            )
            result = search_hub(hub, "steaklovers paginator", top=5, log_metrics=False)
            self.assertIn("steaklovers-dev.md", result["hits"][0]["path"])

    def test_tag_only_match_surfaces_without_body_hit(self) -> None:
        # Query term only in the label, not the body text.
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _write(
                hub,
                "chats/projects/Trendymen.md",
                "_Last updated: 2026-07-11_\n\n"
                "## Open threads\n\n- **[steaklovers-seo]** wire the cover crop · _upd 2026-07-11_\n",
            )
            result = search_hub(hub, "steaklovers", top=5, log_metrics=False)
            self.assertTrue(any("steaklovers-seo" in h["text"] for h in result["hits"]))

    def test_unrelated_query_does_not_falsely_match_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            _write(
                hub,
                "chats/projects/steaklovers-dev.md",
                "_Last updated: 2026-07-10_\n\n## Decisions\n\n- [curated] paginator fix\n",
            )
            result = search_hub(hub, "kubernetes helm chart", top=5, log_metrics=False)
            self.assertEqual(result["hits"], [])


if __name__ == "__main__":
    unittest.main()
