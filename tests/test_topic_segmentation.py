"""Tests for scripts/lib/topic_segmentation.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import topic_segmentation as ts  # noqa: E402


class TestTopicSegmentation(unittest.TestCase):
    def test_new_task_cue_splits(self) -> None:
        msgs = ["work on deploy", "new task: refactor auth module"]
        segs = ts.segment_messages(msgs)
        self.assertEqual(len(segs), 2)

    def test_pause_gap_splits(self) -> None:
        msgs = ["first block about docker", "second block about auth"]
        stamps = ["2026-06-08T10:00:00", "2026-06-08T11:00:00"]
        segs = ts.segment_messages(msgs, timestamps=stamps, pause_minutes=30)
        self.assertEqual(len(segs), 2)

    def test_single_segment_returns_empty(self) -> None:
        segs = ts.segment_messages(["only one topic here"])
        self.assertEqual(segs, [])


if __name__ == "__main__":
    unittest.main()
