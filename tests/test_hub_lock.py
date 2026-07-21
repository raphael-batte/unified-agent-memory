"""Tests for scripts/lib/hub_lock.py — shared hub write protocol."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import hub_lock  # noqa: E402


class TestLockPath(unittest.TestCase):
    def test_matches_cron_script_convention(self) -> None:
        """Cursor's sync-if-cursor-open.sh locks this exact path — must not diverge."""
        hub = Path("/tmp/example-hub")
        self.assertEqual(
            hub_lock.lock_path(hub), hub / ".state" / "periodic-sync.lock"
        )
        script = (
            Path(__file__).resolve().parents[1] / "scripts" / "sync-if-cursor-open.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('LOCK_DIR="$MEMORY_HOME/.state/periodic-sync.lock"', script)


class TestAcquireRelease(unittest.TestCase):
    def test_acquires_and_releases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            path = hub_lock.lock_path(hub)
            with hub_lock.hub_lock(hub):
                self.assertTrue(path.is_dir())
            self.assertFalse(path.exists())

    def test_released_after_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            with self.assertRaises(ValueError):
                with hub_lock.hub_lock(hub):
                    raise ValueError("boom")
            self.assertFalse(hub_lock.lock_path(hub).exists())

    def test_owner_breadcrumb_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            with hub_lock.hub_lock(hub, owner="claude-stop") as path:
                data = json.loads((path / "owner.json").read_text(encoding="utf-8"))
                self.assertEqual(data["owner"], "claude-stop")
                self.assertEqual(data["pid"], os.getpid())


class TestContention(unittest.TestCase):
    def test_busy_raises_within_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hub_lock.lock_path(hub).mkdir(parents=True)
            started = time.monotonic()
            with self.assertRaises(hub_lock.HubBusy):
                with hub_lock.hub_lock(hub, timeout=0.2):
                    pass
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 2.0, "hook must not block the user")

    def test_cron_lock_blocks_hook(self) -> None:
        """A shell `mkdir` lock (what the cron path does) is honoured by the hook path."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            lock = hub_lock.lock_path(hub)
            lock.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["mkdir", str(lock)], check=True)
            with self.assertRaises(hub_lock.HubBusy):
                with hub_lock.hub_lock(hub, timeout=0.1):
                    pass
            subprocess.run(["rmdir", str(lock)], check=True)
            with hub_lock.hub_lock(hub, timeout=0.5):
                pass

    def test_waits_then_acquires_when_freed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            lock = hub_lock.lock_path(hub)
            lock.mkdir(parents=True)

            import threading

            threading.Timer(0.1, lambda: lock.rmdir()).start()
            with hub_lock.hub_lock(hub, timeout=3.0):
                self.assertTrue(lock.is_dir())

    def test_stale_lock_taken_over(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            lock = hub_lock.lock_path(hub)
            lock.mkdir(parents=True)
            old = time.time() - 3600
            os.utime(lock, (old, old))
            with hub_lock.hub_lock(hub, timeout=0.2, stale_after=60):
                self.assertTrue(lock.is_dir())
            self.assertFalse(lock.exists())

    def test_fresh_lock_not_taken_over(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hub_lock.lock_path(hub).mkdir(parents=True)
            with self.assertRaises(hub_lock.HubBusy):
                with hub_lock.hub_lock(hub, timeout=0.1, stale_after=600):
                    pass


class TestAtomicWrite(unittest.TestCase):
    def test_write_creates_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chats" / "manifest.json"
            hub_lock.write_json_atomic(target, {"processed": []})
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")), {"processed": []}
            )

    def test_overwrite_leaves_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notes.md"
            hub_lock.write_atomic(target, "first\n")
            hub_lock.write_atomic(target, "second\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "second\n")
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name != "notes.md"]
            self.assertEqual(leftovers, [])

    def test_reader_never_sees_partial_file(self) -> None:
        """Old content stays fully readable until the replace lands."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "projects.md"
            hub_lock.write_atomic(target, "## Open threads\n- old\n")
            original = target.read_text(encoding="utf-8")
            big = "## Open threads\n" + "- new\n" * 20000
            hub_lock.write_atomic(target, big)
            self.assertEqual(target.read_text(encoding="utf-8"), big)
            self.assertNotEqual(original, big)

    def test_failed_write_keeps_previous_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notes.md"
            hub_lock.write_atomic(target, "keep me\n")

            with self.assertRaises(TypeError):
                hub_lock.write_atomic(target, object())  # type: ignore[arg-type]
            self.assertEqual(target.read_text(encoding="utf-8"), "keep me\n")
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name != "notes.md"]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
