"""Tests for scripts/lib/decision_extract.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.decision_extract import extract_decision_candidates  # noqa: E402


class TestDecisionExtract(unittest.TestCase):
    def test_commitment_cue_scanned_from_all_messages(self) -> None:
        msgs = ["noise"] * 50
        msgs.append(
            "okay then the folder is named home not landing like grafana products"
        )
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "commitment")
        self.assertGreater(out[0]["message_index"], 40)
        self.assertEqual(stats["junk"], 0)

    def test_correction_preferred(self) -> None:
        msgs = [
            "okay then we use home folder naming convention for assets",
            "do not use blueprints in templates — out of scope and confusing",
        ]
        out, _stats = extract_decision_candidates(msgs, max_items=6)
        self.assertGreaterEqual(len(out), 1)
        sources = {row["source"] for row in out}
        self.assertIn("correction", sources)

    def test_rejects_ci_log_paste(self) -> None:
        msgs = [
            "Run `npm test` Packages in scope: 12 WARNINGS: 3 "
            "okay then we should use home folder"
        ]
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(out, [])
        self.assertGreater(stats["junk"], 0)

    def test_rejects_press_release_with_late_cue(self) -> None:
        msgs = [
            "How about IRM future? Press Release: Grafana Labs announces "
            "okay then home folder is correct"
        ]
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(out, [])
        self.assertGreater(stats["position"] + stats["junk"], 0)

    def test_rejects_plain_question(self) -> None:
        msgs = ["Do we need to create a new API key for this deploy?"]
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(out, [])
        self.assertGreater(stats["question"], 0)

    def test_allows_negation_question(self) -> None:
        msgs = ["Do not use blogs in sitemap — we block them via robots.txt now"]
        out, _stats = extract_decision_candidates(msgs, max_items=6)
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "correction")

    def test_accepts_short_landing_decision(self) -> None:
        msgs = ["okay then fewer tests for landing page — keep smoke only"]
        out, _stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(len(out), 1)
        self.assertIn("landing", out[0]["text"].lower())

    def test_rejects_ru_affirmative_question(self) -> None:
        msgs = [
            "\u043c\u043d\u0435 \u043d\u0430\u0434\u043e \u043d\u043e\u0432\u044b\u0439 "
            "\u043a\u043b\u044e\u0447 \u0441\u043e\u0437\u0434\u0430\u0442\u044c?"
        ]
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(out, [])
        self.assertGreater(stats["question"], 0)

    def test_rejects_ru_question_with_late_negation_word(self) -> None:
        msgs = [
            "\u0442\u0430\u043a\u043e\u0439 \u0438\u043a\u043e\u043d\u043a\u0438 "
            "\u043d\u0435\u0442 \u0434\u043b\u044f \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u0430?"
        ]
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(out, [])
        self.assertGreater(stats["question"], 0)

    def test_allows_negation_at_message_start_ru(self) -> None:
        msgs = [
            "\u043d\u0435 \u043d\u0430\u0434\u043e \u0442\u0430\u043c "
            "\u0431\u043b\u044e\u043f\u0440\u0438\u043d\u0442\u044b \u2014 "
            "out of scope for this release cycle"
        ]
        out, _stats = extract_decision_candidates(msgs, max_items=6)
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "correction")

    def test_rejects_lighthouse_json(self) -> None:
        msgs = [
            '{ "lighthouseVersion": "13.0.2", "requestedUrl": "https://example.org/" }'
        ]
        out, stats = extract_decision_candidates(msgs, max_items=6)
        self.assertEqual(out, [])
        self.assertGreater(stats["junk"], 0)


if __name__ == "__main__":
    unittest.main()
