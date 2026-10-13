"""Tests for scripts/lib/extracted_repair.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import lang_cues as lc  # noqa: E402
from lib.extracted_repair import apply_repairs, find_repairs  # noqa: E402

CHAT_ID = "repair-chat-0001"
CLEAN = "- [extracted] keep the staging rollout behind a feature flag for now"
CUT_REBUILD = "- [extracted] y then migrate the alpha-hub database tonight please"
CUT_DROP = "- [extracted] hip the canary build to all beta users by friday"
CUT_WORD = "- [extracted] the canary rollout needs a manual approval step"
UNTRACED = "- [extracted] something that is not in any transcript at all"


def _hub(root: Path) -> Path:
    hub = root / "hub"
    (hub / "chats" / "projects").mkdir(parents=True)
    (hub / "transcripts").mkdir()
    rows = [
        "okay then keep the staging rollout behind a feature flag for now",
        "okay then migrate the alpha-hub database tonight please",
        "ship the canary build to all beta users by friday",
        # a pasted report quoting the damaged bullet must not count as a clean source
        "look at this: [extracted] hip the canary build to all beta users by friday",
        # a long paste with the same words far from the start is not where the cut came from
        # a leading function word stripped at a word boundary is damage too
        "of the canary rollout needs a manual approval step",
        "x" * 300 + " please ship the canary build to all beta users by friday",
    ]
    (hub / "transcripts" / f"{CHAT_ID}.jsonl").write_text(
        "\n".join(json.dumps({"role": "user", "content": r}) for r in rows) + "\n",
        encoding="utf-8",
    )
    (hub / "chats" / "manifest.json").write_text(
        json.dumps(
            {
                "processed": [
                    {"id": CHAT_ID, "distilled_to": ["projects/example-app.md"]}
                ],
                "pending": [],
            }
        ),
        encoding="utf-8",
    )
    (hub / "chats" / "projects" / "example-app.md").write_text(
        "# example-app\n\n## Decisions\n\n"
        + "\n".join([CLEAN, CUT_REBUILD, CUT_DROP, CUT_WORD, UNTRACED])
        + "\n\n## Open threads\n\n",
        encoding="utf-8",
    )
    return hub


class TestExtractedRepair(unittest.TestCase):
    def setUp(self) -> None:
        lc.clear_lang_cue_cache()

    def test_only_mid_word_bullets_are_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            repairs, stats = find_repairs(hub)
            self.assertEqual(stats["truncated"], 3)
            self.assertEqual(stats["untraced"], 1)
            by_old = {r.old: r.new for r in repairs}
            self.assertNotIn(CLEAN, by_old)
            self.assertEqual(
                by_old[CUT_REBUILD],
                "- [extracted] migrate the alpha-hub database tonight please",
            )
            self.assertIsNone(by_old[CUT_DROP])
            self.assertIsNone(by_old[CUT_WORD])

    def test_apply_backs_up_and_rewrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            project = hub / "chats" / "projects" / "example-app.md"
            original = project.read_text(encoding="utf-8")
            repairs, _stats = find_repairs(hub)
            result = apply_repairs(hub, repairs)

            text = project.read_text(encoding="utf-8")
            self.assertIn(CLEAN, text)
            self.assertIn(UNTRACED, text)
            self.assertNotIn(CUT_REBUILD, text)
            self.assertNotIn(CUT_DROP, text)
            self.assertIn("migrate the alpha-hub database tonight please", text)
            self.assertIn("## Open threads", text)

            backup = Path(result["backup"]) / "projects" / "example-app.md"
            self.assertEqual(backup.read_text(encoding="utf-8"), original)
            self.assertTrue(backup.parent.parent.name.startswith("projects-backup-"))

            again, _ = find_repairs(hub)
            self.assertEqual(again, [])


if __name__ == "__main__":
    unittest.main()
