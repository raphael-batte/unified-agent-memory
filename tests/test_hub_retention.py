"""Tests for scripts/lib/hub_retention.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.hub_retention import cleanup_hub_artifacts  # noqa: E402


class TestHubRetention(unittest.TestCase):
    def test_deletes_stale_processed_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            chat_id = "abcd-1234-5678-90ab-cdef12345678"
            (hub / "chats").mkdir(parents=True)
            (hub / "chats" / "extracts").mkdir()
            (hub / "chats" / "manifest.json").write_text(
                json.dumps({"processed": [{"id": chat_id}], "pending": []}),
                encoding="utf-8",
            )
            stale = hub / "chats" / "extracts" / f"{chat_id}.json"
            stale.write_text("{}", encoding="utf-8")
            old = datetime.now() - timedelta(days=40)
            import os

            os.utime(stale, (old.timestamp(), old.timestamp()))
            result = cleanup_hub_artifacts(hub, retention_days=30, dry_run=False)
            self.assertEqual(result["deleted"], 1)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
