"""Tests for scripts/lib/lang_learn.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import lang_cues as lc  # noqa: E402
from lib import lang_learn as ll  # noqa: E402
from lib.distill_metrics import read_metrics  # noqa: E402


class TestLangLearn(unittest.TestCase):
    def setUp(self) -> None:
        lc.clear_lang_cue_cache()

    def test_project_lang_cues_applies_thresholds(self) -> None:
        doc = ll._empty_doc()
        doc["categories"]["commitment_prefixes"] = [
            {
                "phrase": "low-signal",
                "count": 1,
                "distinct_chats": ["a"],
                "example_context": "x",
            },
            {
                "phrase": "ok then run tests",
                "count": 4,
                "distinct_chats": ["a", "b", "c"],
                "example_context": "y",
            },
        ]
        flat = ll.project_lang_cues(doc, min_count=2, min_distinct=2)
        self.assertNotIn("low-signal", flat["commitment_prefixes"])
        self.assertIn("ok then run tests", flat["commitment_prefixes"])

    def test_mine_idempotent_by_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            jsonl = hub / "chat.jsonl"
            lines = [
                {
                    "role": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Should we deploy now?"}
                        ]
                    },
                },
                {
                    "role": "user",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "okay then run ./scripts/resync-all.sh on prod",
                            }
                        ]
                    },
                },
            ]
            jsonl.write_text(
                "\n".join(json.dumps(row) for row in lines) + "\n",
                encoding="utf-8",
            )
            pending = [{"id": "chat-1", "jsonl": jsonl}]
            doc = ll._empty_doc()
            doc = ll.mine_into_doc(doc, pending, memory_home=hub)
            first_count = doc["categories"]["commitment_prefixes"][0]["count"]
            doc = ll.mine_into_doc(doc, pending, memory_home=hub)
            second_count = doc["categories"]["commitment_prefixes"][0]["count"]
            self.assertEqual(first_count, second_count)

    def test_prepare_writes_and_emits_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / ".state").mkdir()
            jsonl = hub / "chat.jsonl"
            jsonl.write_text(
                json.dumps(
                    {
                        "role": "user",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "please run ./scripts/run-device.sh and record session",
                                }
                            ]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            pending = [{"id": "c1", "jsonl": jsonl}]
            out = ll.prepare_lang_learn_for_batch(hub, pending, force=True)
            self.assertEqual(out.get("event"), "lang_learn_summary")
            self.assertTrue(ll.lang_learned_path(hub).is_file())
            rows = read_metrics(hub)
            self.assertTrue(any(r.get("event") == "lang_learn_summary" for r in rows))

    def test_load_lang_cues_includes_learned_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            doc = ll._empty_doc()
            doc["categories"]["user_action_verbs"] = [
                {
                    "phrase": "zapusti",
                    "count": 3,
                    "distinct_chats": ["a", "b"],
                    "example_context": "zapusti test",
                }
            ]
            ll.write_lang_learned(hub, doc)
            lc.clear_lang_cue_cache()
            cues = lc.load_lang_cues(memory_home=hub)
            self.assertIn("zapusti", cues["user_action_verbs"])


if __name__ == "__main__":
    unittest.main()
