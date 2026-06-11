"""Tests for scripts/lib/pointer_metrics.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.distill_metrics import read_metrics  # noqa: E402
from lib.pointer_metrics import maybe_log_pointer_clobbered  # noqa: E402


class TestPointerMetrics(unittest.TestCase):
    def test_clobber_logged_when_other_chat_in_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            existing = [
                "- [older task](aaaa-bbbb-cccc-dddd-eeee-ffff-0000) distilled 2026-06-01",
            ]
            maybe_log_pointer_clobbered(
                hub,
                workspace_slug="app",
                new_chat_id="new-chat-uuid-1111",
                existing_recent=existing,
                prev_next_step="Deploy security patch to production",
                next_kind="extracted",
            )
            rows = read_metrics(hub)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event"], "pointer_clobbered_cross_chat")
            self.assertIn("aaaa-bbbb", rows[0]["other_chat_ids"][0])

    def test_clobber_skipped_without_prev_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            maybe_log_pointer_clobbered(
                hub,
                workspace_slug="app",
                new_chat_id="x",
                existing_recent=["- [q](other-id-12345678)"],
                prev_next_step=None,
                next_kind="extracted",
            )
            self.assertEqual(read_metrics(hub), [])

    def test_clobber_skipped_for_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            maybe_log_pointer_clobbered(
                hub,
                workspace_slug="app",
                new_chat_id="x",
                existing_recent=["- [q](other-id-12345678)"],
                prev_next_step="Old step",
                next_kind="placeholder_empty",
            )
            self.assertEqual(read_metrics(hub), [])


if __name__ == "__main__":
    unittest.main()
