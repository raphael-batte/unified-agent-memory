"""Tests for scripts/lib/lang_cues.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import lang_cues as lc  # noqa: E402
from lib.distill_metrics import read_metrics  # noqa: E402


class TestLangCues(unittest.TestCase):
    def setUp(self) -> None:
        lc.clear_lang_cue_cache()

    def test_load_merges_en_and_ru(self) -> None:
        cues = lc.load_lang_cues()
        self.assertIn("next step", [m.lower() for m in cues["next_step_markers"]])
        self.assertTrue(any("\u0441\u043b\u0435\u0434" in m for m in cues["next_step_markers"]))

    def test_build_line_patterns_ru_marker(self) -> None:
        cues = lc.load_lang_cues()
        patterns = lc.build_line_patterns(cues)
        blob = "\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0448\u0430\u0433: \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0442\u0435\u0441\u0442\u044b \u043d\u0430 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0435"
        matched = any(p.search(blob) for p in patterns)
        self.assertTrue(matched)

    def test_hub_lang_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "config.json").write_text(
                json.dumps(
                    {
                        "lang": {
                            "commitment_prefixes": ["custom-prefix-go"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            cues = lc.load_lang_cues(memory_home=hub)
            pat = lc.build_commitment_pattern(cues)
            self.assertIsNotNone(pat.search("custom-prefix-go deploy the staging stack"))

    def test_invalid_hub_lang_logs_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "config.json").write_text(
                json.dumps({"lang": {"correction_cues": "not-a-list"}}),
                encoding="utf-8",
            )
            lc.load_lang_cues(memory_home=hub)
            rows = read_metrics(hub)
            events = [r.get("event") for r in rows]
            self.assertIn("lang_config_invalid", events)


if __name__ == "__main__":
    unittest.main()
