"""Tests for rolling summary compaction."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.pointer_curation_queue import list_pending  # noqa: E402
from lib.rolling_distill import mechanical_compact_segments, update_rolling_after_merge  # noqa: E402


class TestRollingCompaction(unittest.TestCase):
    def test_mechanical_compact_dedups(self) -> None:
        segments = [
            {"bullets": ["Deploy docker to production server"]},
            {"bullets": ["Deploy docker to production server", "Add smoke tests"]},
        ]
        compact, summary = mechanical_compact_segments(segments)
        self.assertEqual(len(summary), 2)

    def test_enqueue_compaction_at_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            segments = [{"from": i, "to": i + 1, "bullets": [f"bullet {i}"]} for i in range(16)]
            from lib.rolling_distill import save_rolling

            save_rolling(
                hub,
                "chat-uuid",
                {"chat_id": "chat-uuid", "last_user_count": 0, "segments": segments},
            )
            update_rolling_after_merge(
                hub,
                "chat-uuid",
                total_user_count=20,
                incremental_bullets=["new bullet here"],
                incremental_from=16,
                workspace_slug="app",
                enqueue_threshold=15,
                hard_cap=25,
            )
            pending = list_pending(hub, kind="compaction")
            self.assertEqual(len(pending), 1)


if __name__ == "__main__":
    unittest.main()
