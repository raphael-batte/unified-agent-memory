"""Tests for scripts/lib/memory_config.py"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import memory_config as mc  # noqa: E402


class TestMemoryConfig(unittest.TestCase):
    def test_resolve_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.assertEqual(
                mc.resolve_memory_home(str(p), script_file=__file__),
                p.resolve(),
            )

    def test_resolve_env_over_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_hub = Path(tmp) / "env-hub"
            env_hub.mkdir()
            anchor_dir = Path(tmp) / "anchor-home"
            anchor_dir.mkdir()
            anchor_file = Path(tmp) / "agent-memory" / "config.json"
            anchor_file.parent.mkdir(parents=True)
            anchor_file.write_text(
                json.dumps({"memory_home": str(anchor_dir)}),
                encoding="utf-8",
            )
            with mock.patch.object(mc, "ANCHOR_FILE", anchor_file):
                with mock.patch.dict(
                    os.environ, {"MEMORY_HOME": str(env_hub)}, clear=False
                ):
                    self.assertEqual(
                        mc.resolve_memory_home(None, script_file=__file__),
                        env_hub.resolve(),
                    )

    def test_resolve_anchor_memory_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "my-hub"
            hub.mkdir()
            anchor_file = Path(tmp) / "cursor" / "agent-memory" / "config.json"
            anchor_file.parent.mkdir(parents=True)
            anchor_file.write_text(
                json.dumps({"memory_home": str(hub)}),
                encoding="utf-8",
            )
            with mock.patch.object(mc, "ANCHOR_FILE", anchor_file):
                with mock.patch.dict(os.environ, {}, clear=True):
                    os.environ.pop("MEMORY_HOME", None)
                    self.assertEqual(
                        mc.resolve_memory_home(None, script_file=__file__),
                        hub.resolve(),
                    )

    def test_default_memory_home_without_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            default_dir = Path(tmp) / "default-hub"
            default_dir.mkdir()
            anchor_file = Path(tmp) / "nope" / "config.json"
            with mock.patch.object(mc, "ANCHOR_FILE", anchor_file):
                with mock.patch.object(mc, "DEFAULT_MEMORY_HOME", default_dir):
                    with mock.patch.object(mc, "_load_legacy_hook_env", return_value={}):
                        with mock.patch.object(
                            mc, "LEGACY_GLOBAL_CONFIG", Path(tmp) / "nope-legacy.json"
                        ):
                            with mock.patch.dict(os.environ, {}, clear=True):
                                os.environ.pop("MEMORY_HOME", None)
                                self.assertEqual(
                                    mc.resolve_memory_home(None, script_file=__file__),
                                    default_dir.resolve(),
                                )

    def test_detect_plugin_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "agent-memory"
            (plugin / ".cursor-plugin").mkdir(parents=True)
            (plugin / ".cursor-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin / "INSTRUCTIONS.md").write_text("# x", encoding="utf-8")
            script = plugin / "hooks" / "boundary.sh"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")
            self.assertEqual(
                mc.detect_plugin_root(script),
                plugin.resolve(),
            )

    def test_plugin_root_from_hub_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            plugin = Path(tmp) / "plugin"
            hub.mkdir()
            plugin.mkdir()
            (plugin / "INSTRUCTIONS.md").write_text("# x", encoding="utf-8")
            (plugin / ".cursor-plugin").mkdir()
            (plugin / ".cursor-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (hub / "config.json").write_text(
                json.dumps({"plugin_root": str(plugin)}),
                encoding="utf-8",
            )
            with mock.patch.object(mc, "_load_legacy_hook_env", return_value={}):
                with mock.patch.dict(os.environ, {}, clear=True):
                    os.environ.pop("FRAMEWORK_ROOT", None)
                    os.environ.pop("AGENT_MEMORY_FRAMEWORK", None)
                    self.assertEqual(
                        mc.resolve_plugin_root(memory_home=hub),
                        plugin.resolve(),
                    )

    def test_persist_anchor_and_hub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "plugin"
            hub = Path(tmp) / "hub"
            plugin.mkdir()
            (plugin / "INSTRUCTIONS.md").write_text("# x", encoding="utf-8")
            anchor_file = Path(tmp) / "anchor" / "config.json"
            with mock.patch.object(mc, "ANCHOR_FILE", anchor_file):
                mc.persist_paths(plugin, hub)
            self.assertEqual(
                json.loads(anchor_file.read_text())["memory_home"],
                str(hub.resolve()),
            )
            hub_cfg = json.loads((hub / "config.json").read_text())
            self.assertEqual(hub_cfg["plugin_root"], str(plugin.resolve()))
            for key in ("handoff_mode", "install_root", "dev_root"):
                self.assertNotIn(key, hub_cfg)

    def test_framework_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fw = Path(tmp)
            (fw / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            self.assertEqual(mc.framework_version(fw), "1.2.3")
            self.assertIsNone(mc.framework_version(None))

    def test_legacy_xdg_emits_deprecation_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy_cfg = Path(tmp) / "legacy.json"
            hub = Path(tmp) / "legacy-hub"
            hub.mkdir()
            legacy_cfg.write_text(
                json.dumps({"memory_home": str(hub)}),
                encoding="utf-8",
            )
            anchor_file = Path(tmp) / "missing-anchor.json"
            with mock.patch.object(mc, "LEGACY_GLOBAL_CONFIG", legacy_cfg):
                with mock.patch.object(mc, "ANCHOR_FILE", anchor_file):
                    with mock.patch.object(mc, "memory_home_from_anchor", return_value=None):
                        with mock.patch.object(mc, "_load_legacy_hook_env", return_value={}):
                            with mock.patch.dict(os.environ, {}, clear=True):
                                with warnings.catch_warnings(record=True) as caught:
                                    warnings.simplefilter("always", DeprecationWarning)
                                    resolved = mc.resolve_memory_home(
                                        None, script_file=None
                                    )
                                self.assertEqual(resolved, hub.resolve())
                                self.assertTrue(
                                    any(
                                        issubclass(w.category, DeprecationWarning)
                                        for w in caught
                                    )
                                )


if __name__ == "__main__":
    unittest.main()
