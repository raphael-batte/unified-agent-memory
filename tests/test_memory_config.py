"""Tests for scripts/lib/memory_config.py"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from lib import memory_config as mc  # noqa: E402


def _anchor_env(anchor_home: Path) -> dict[str, str]:
    return {"AGENT_MEMORY_ANCHOR_HOME": str(anchor_home)}


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
            anchor_home = Path(tmp) / "anchor-home"
            hub_in_anchor = Path(tmp) / "hub-from-anchor"
            hub_in_anchor.mkdir()
            anchor_file = anchor_home / ".cursor" / "agent-memory" / "config.json"
            anchor_file.parent.mkdir(parents=True)
            anchor_file.write_text(
                json.dumps({"memory_home": str(hub_in_anchor)}),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {**_anchor_env(anchor_home), "MEMORY_HOME": str(env_hub)},
                clear=False,
            ):
                self.assertEqual(
                    mc.resolve_memory_home(None, script_file=__file__),
                    env_hub.resolve(),
                )

    def test_resolve_anchor_memory_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "my-hub"
            hub.mkdir()
            anchor_home = Path(tmp) / "fake-home"
            anchor_file = anchor_home / ".cursor" / "agent-memory" / "config.json"
            anchor_file.parent.mkdir(parents=True)
            anchor_file.write_text(
                json.dumps({"memory_home": str(hub)}),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                _anchor_env(anchor_home),
                clear=True,
            ):
                os.environ.pop("MEMORY_HOME", None)
                self.assertEqual(
                    mc.resolve_memory_home(None, script_file=__file__),
                    hub.resolve(),
                )

    def _resolve_with_fake_home(self, anchor_home: Path, tmp: str) -> Path:
        with mock.patch.object(mc, "_load_legacy_hook_env", return_value={}):
            with mock.patch.object(
                mc, "LEGACY_GLOBAL_CONFIG", Path(tmp) / "nope-legacy.json"
            ):
                with mock.patch.dict(os.environ, _anchor_env(anchor_home), clear=True):
                    os.environ.pop("MEMORY_HOME", None)
                    return mc.resolve_memory_home(None, script_file=__file__)

    def test_default_memory_home_is_environment_neutral(self) -> None:
        """A fresh install lands on the shared hub, not inside one environment's dir."""
        with tempfile.TemporaryDirectory() as tmp:
            anchor_home = Path(tmp) / "fake-home"
            expected = anchor_home / ".agent-memory"
            self.assertEqual(self._resolve_with_fake_home(anchor_home, tmp), expected.resolve())

    def test_legacy_hub_inside_anchor_dir_still_wins(self) -> None:
        """Older installs kept hub data in the anchor dir — do not orphan it."""
        with tempfile.TemporaryDirectory() as tmp:
            anchor_home = Path(tmp) / "fake-home"
            legacy = anchor_home / ".cursor" / "agent-memory"
            (legacy / "chats" / "projects").mkdir(parents=True)
            self.assertEqual(self._resolve_with_fake_home(anchor_home, tmp), legacy.resolve())

    def test_other_environments_anchor_is_inherited(self) -> None:
        """Whichever environment is installed second joins the existing hub."""
        with tempfile.TemporaryDirectory() as tmp:
            anchor_home = Path(tmp) / "fake-home"
            shared = Path(tmp) / "shared-hub"
            shared.mkdir()
            claude_anchor = anchor_home / ".claude" / "agent-memory"
            claude_anchor.mkdir(parents=True)
            (claude_anchor / "config.json").write_text(
                json.dumps({"memory_home": str(shared)}), encoding="utf-8"
            )
            # Resolving as Cursor, whose own anchor does not exist yet.
            with mock.patch.dict(os.environ, {"AGENT_MEMORY_ENV": "cursor"}, clear=False):
                self.assertEqual(
                    self._resolve_with_fake_home(anchor_home, tmp), shared.resolve()
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
            anchor_home = Path(tmp) / "anchor-home"
            with mock.patch.dict(os.environ, _anchor_env(anchor_home), clear=False):
                mc.persist_paths(plugin, hub)
            anchor_file = anchor_home / ".cursor" / "agent-memory" / "config.json"
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
            anchor_home = Path(tmp) / "no-anchor"
            with mock.patch.object(mc, "LEGACY_GLOBAL_CONFIG", legacy_cfg):
                with mock.patch.dict(
                    os.environ,
                    _anchor_env(anchor_home),
                    clear=True,
                ):
                    with mock.patch.object(mc, "memory_home_from_anchor", return_value=None):
                        with mock.patch.object(mc, "_load_legacy_hook_env", return_value={}):
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

    def test_init_memory_subprocess_does_not_touch_production_anchor(self) -> None:
        """Regression: subprocess init-memory must respect AGENT_MEMORY_ANCHOR_HOME."""
        with tempfile.TemporaryDirectory() as tmp:
            production_home = Path(tmp) / "production-home"
            test_home = Path(tmp) / "test-home"
            production_hub = Path(tmp) / "production-hub"
            test_hub = Path(tmp) / "test-hub"
            production_hub.mkdir()
            (production_hub / "chats").mkdir()
            (production_hub / "chats" / "manifest.json").write_text(
                json.dumps(
                    {
                        "processed": [{"id": "keep-me", "distilled_at": "2026-06-01"}],
                        "pending": [],
                    }
                ),
                encoding="utf-8",
            )
            production_anchor = (
                production_home / ".cursor" / "agent-memory" / "config.json"
            )
            production_anchor.parent.mkdir(parents=True)
            production_anchor.write_text(
                json.dumps({"memory_home": str(production_hub.resolve())}),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["AGENT_MEMORY_ANCHOR_HOME"] = str(test_home)
            env["MEMORY_HOME"] = str(test_hub)
            env.pop("MEMORY_HOME_OVERRIDE", None)

            proc = subprocess.run(
                ["bash", str(REPO / "scripts" / "init-memory.sh")],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                proc.returncode,
                0,
                proc.stderr or proc.stdout,
            )

            prod_cfg = json.loads(production_anchor.read_text())
            self.assertEqual(prod_cfg["memory_home"], str(production_hub.resolve()))

            test_anchor = test_home / ".cursor" / "agent-memory" / "config.json"
            self.assertTrue(test_anchor.is_file(), "isolated anchor should be written")
            test_cfg = json.loads(test_anchor.read_text())
            self.assertEqual(test_cfg["memory_home"], str(test_hub.resolve()))

    def test_real_anchor_refuses_temp_hub(self) -> None:
        """Regression: a test file run standalone must not anchor $HOME at $TMPDIR.

        tests/run-tests.sh pins AGENT_MEMORY_ANCHOR_HOME; a single test file run
        on its own does not, so without this guard it rewrites the developer's
        real anchor to a scratch hub the OS later deletes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            temp_hub = Path(tmp) / "hub"
            temp_hub.mkdir()
            fake_home = Path("/nonexistent-agent-memory-home")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AGENT_MEMORY_ANCHOR_HOME", None)
                with mock.patch.object(Path, "home", staticmethod(lambda: fake_home)):
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        self.assertEqual(mc.persist_all_anchors(temp_hub), [])
                        mc.persist_anchor(temp_hub)
                    self.assertTrue(
                        any("temp hub" in str(w.message) for w in caught),
                        "refusal should warn",
                    )
            self.assertFalse(fake_home.exists(), "must not create a real anchor")

    def test_temp_anchor_still_accepts_temp_hub(self) -> None:
        """Tests that pin the anchor root to tmp keep working — the guard is the pair."""
        with tempfile.TemporaryDirectory() as tmp:
            anchor_home = Path(tmp) / "anchor-home"
            temp_hub = Path(tmp) / "hub"
            temp_hub.mkdir()
            with mock.patch.dict(os.environ, _anchor_env(anchor_home), clear=False):
                written = mc.persist_all_anchors(temp_hub)
            self.assertEqual(len(written), len(mc.ANCHOR_RELATIVE_DIRS))
            for path in written:
                self.assertEqual(
                    json.loads(path.read_text())["memory_home"],
                    str(temp_hub.resolve()),
                )


if __name__ == "__main__":
    unittest.main()
