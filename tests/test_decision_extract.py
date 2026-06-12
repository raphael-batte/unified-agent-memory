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
        out = extract_decision_candidates(msgs, max_items=6)
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "commitment")
        self.assertGreater(out[0]["message_index"], 40)

    def test_correction_preferred(self) -> None:
        msgs = [
            "okay then we use home folder naming convention for assets",
            "do not use blueprints in templates — out of scope and confusing",
        ]
        out = extract_decision_candidates(msgs, max_items=6)
        self.assertGreaterEqual(len(out), 1)
        sources = {row["source"] for row in out}
        self.assertIn("correction", sources)


if __name__ == "__main__":
    unittest.main()
