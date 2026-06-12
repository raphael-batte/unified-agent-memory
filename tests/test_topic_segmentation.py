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
        msgs = [
            "work on deploy pipeline with enough words",
            "still on deploy topic with more context",
            "third line before switch with enough padding",
            "new task: refactor auth module for production",
            "auth module follow up with more detail here",
            "another auth line to keep segment size",
        ]
        segs = ts.segment_messages(msgs, min_segment_msgs=3)
        self.assertEqual(len(segs), 2)
        self.assertEqual(sum(s["count"] for s in segs), len(msgs))

    def test_pause_gap_splits(self) -> None:
        msgs = [
            "first block about docker deploy setup",
            "more docker context with enough words",
            "third docker line before pause gap",
            "second block about auth module design",
            "auth follow up with enough detail",
            "another auth message for segment size",
        ]
        stamps = [
            "2026-06-08T10:00:00",
            "2026-06-08T10:05:00",
            "2026-06-08T10:10:00",
            "2026-06-08T11:00:00",
            "2026-06-08T11:05:00",
            "2026-06-08T11:10:00",
        ]
        segs = ts.segment_messages(
            msgs, timestamps=stamps, pause_minutes=30, min_segment_msgs=3
        )
        self.assertEqual(len(segs), 2)
        self.assertEqual(sum(s["count"] for s in segs), len(msgs))

    def test_single_segment_returns_empty(self) -> None:
        segs = ts.segment_messages(["only one topic here"])
        self.assertEqual(segs, [])

    def test_long_chat_full_coverage(self) -> None:
        msgs = []
        for i in range(120):
            if i in (0, 1, 2, 40, 80):
                msgs.append(f"new task: topic block {i // 40}")
            else:
                msgs.append(f"message {i} about topic {i // 40} with enough words here")
        segs = ts.segment_messages(msgs, max_segments=6, min_segment_msgs=3)
        self.assertGreater(len(segs), 1)
        self.assertLessEqual(len(segs), 6)
        self.assertEqual(sum(s["count"] for s in segs), len(msgs))
        self.assertEqual(segs[0]["start"], 0)
        self.assertEqual(segs[-1]["start"] + segs[-1]["count"], len(msgs))

    def test_dense_early_breaks_do_not_drop_tail(self) -> None:
        msgs = []
        for i in range(80):
            if i < 10:
                msgs.append(f"new task: micro task {i} with padding text")
            else:
                msgs.append(
                    f"long tail message {i} about schedule layers polishing details"
                )
        segs = ts.segment_messages(msgs, max_segments=6, min_segment_msgs=3)
        self.assertTrue(segs)
        self.assertEqual(sum(s["count"] for s in segs), len(msgs))
        self.assertGreater(segs[-1]["start"], 9)


if __name__ == "__main__":
    unittest.main()
