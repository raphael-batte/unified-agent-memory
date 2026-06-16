"""Tests for scripts/lib/doctor_fix.py"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import doctor_fix as df  # noqa: E402
from lib import memory_config as mc  # noqa: E402


class TestDoctorFix(unittest.TestCase):
    def test_fix_updates_hub_config_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "memory"
            hub.mkdir()
            fw = Path(tmp) / "clone"
            fw.mkdir()
            (fw / "INSTRUCTIONS.md").write_text("# x", encoding="utf-8")
            (hub / "config.json").write_text('{"framework_root": "/old"}', encoding="utf-8")
            report = df.run_fix(memory_home=hub, framework_root=fw, dry_run=True)
            self.assertTrue(report["ok"])
            self.assertTrue(any("would set anchor + hub" in a for a in report["actions"]))

    def test_fix_writes_hub_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "memory"
            hub.mkdir()
            fw = Path(tmp) / "clone"
            fw.mkdir()
            (fw / "INSTRUCTIONS.md").write_text("# x", encoding="utf-8")
            anchor_home = Path(tmp) / "anchor-home"
            with mock.patch.dict(
                os.environ,
                {"AGENT_MEMORY_ANCHOR_HOME": str(anchor_home)},
                clear=False,
            ):
                report = df.run_fix(memory_home=hub, framework_root=fw, dry_run=False)
            self.assertTrue(report["ok"])
            cfg = json.loads((hub / "config.json").read_text())
            self.assertEqual(Path(cfg["framework_root"]).resolve(), fw.resolve())

    def test_fix_preserves_initialized_anchor_without_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            anchor_home = Path(tmp) / "anchor-home"
            real_hub = Path(tmp) / "real-hub"
            stray_hub = Path(tmp) / "stray-hub"
            fw = Path(tmp) / "clone"
            for d in (real_hub, stray_hub, fw):
                d.mkdir()
            (fw / "INSTRUCTIONS.md").write_text("# x", encoding="utf-8")
            (real_hub / "chats").mkdir()
            (real_hub / "chats" / "manifest.json").write_text(
                json.dumps({"processed": [{"id": "x"}], "pending": []}),
                encoding="utf-8",
            )
            anchor_file = anchor_home / ".cursor" / "agent-memory" / "config.json"
            anchor_file.parent.mkdir(parents=True)
            anchor_file.write_text(
                json.dumps({"memory_home": str(real_hub.resolve())}),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"AGENT_MEMORY_ANCHOR_HOME": str(anchor_home)},
                clear=False,
            ):
                report = df.run_fix(
                    memory_home=stray_hub,
                    framework_root=fw,
                    dry_run=False,
                    memory_home_cli=False,
                )
            self.assertTrue(report["ok"])
            self.assertTrue(
                any("preserved anchor memory_home" in a for a in report["actions"])
            )
            anchor_cfg = json.loads(anchor_file.read_text())
            self.assertEqual(anchor_cfg["memory_home"], str(real_hub.resolve()))


if __name__ == "__main__":
    unittest.main()
