"""Tests for pointer provenance classes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.pointer_provenance import (  # noqa: E402
    PROVENANCE_AGENT_LIVE,
    PROVENANCE_STRONG_SIGNAL,
    normalize_provenance,
    pointer_provenance_class,
)


class TestPointerProvenance(unittest.TestCase):
    def test_strong_signal_sources(self) -> None:
        self.assertEqual(
            pointer_provenance_class("user_commitment"), PROVENANCE_STRONG_SIGNAL
        )
        self.assertEqual(pointer_provenance_class("todo_state"), PROVENANCE_STRONG_SIGNAL)

    def test_agent_live(self) -> None:
        self.assertEqual(pointer_provenance_class("agent_live"), PROVENANCE_AGENT_LIVE)

    def test_legacy_live_normalized(self) -> None:
        self.assertEqual(normalize_provenance("live"), PROVENANCE_STRONG_SIGNAL)


if __name__ == "__main__":
    unittest.main()
