"""Tests for scripts/lib/doctor_fix.py"""

from __future__ import annotations

import json
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
            anchor_file = Path(tmp) / "anchor" / "config.json"
            with mock.patch.object(mc, "ANCHOR_FILE", anchor_file):
                report = df.run_fix(memory_home=hub, framework_root=fw, dry_run=False)
            self.assertTrue(report["ok"])
            cfg = json.loads((hub / "config.json").read_text())
            self.assertEqual(Path(cfg["framework_root"]).resolve(), fw.resolve())


if __name__ == "__main__":
    unittest.main()
