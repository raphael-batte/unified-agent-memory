"""Tests for pointer curation queue."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import pointer_curation_queue as pcq  # noqa: E402


class TestPointerQueue(unittest.TestCase):
    def test_enqueue_and_session_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            pcq.enqueue(
                hub,
                chat_id="abc",
                project_rel="chats/projects/foo.md",
                reason="placeholder_empty",
                workspace_slug="foo",
            )
            msg = pcq.session_start_user_message(hub, ["/tmp/workspaces/foo"])
            self.assertIsNotNone(msg)
            self.assertIn("foo.md", msg or "")
            self.assertTrue(pcq.mark_done(hub, "abc"))
            self.assertIsNone(pcq.session_start_user_message(hub, ["/tmp/workspaces/foo"]))


if __name__ == "__main__":
    unittest.main()
