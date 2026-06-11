"""Shared path resolution — plugin bundle + external hub (anchor)."""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

PLUGIN_MANIFEST = ".cursor-plugin/plugin.json"
# Fixed anchor (survives bundle updates)
ANCHOR_DIR = Path.home() / ".cursor" / "agent-memory"
ANCHOR_FILE = ANCHOR_DIR / "config.json"
DEFAULT_MEMORY_HOME = ANCHOR_DIR
# Legacy read-only fallbacks
LEGACY_GLOBAL_CONFIG = Path.home() / ".config" / "cursor-agent-memory" / "config.json"
LEGACY_HOOK_ENV = Path.home() / ".cursor" / "hooks" / "agent-memory.env"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_legacy_hook_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not LEGACY_HOOK_ENV.is_file():
        return out
    for line in LEGACY_HOOK_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip("'\"")
    return out


def load_anchor_config() -> dict:
    return _read_json(ANCHOR_FILE)


def memory_home_from_anchor() -> Path | None:
    raw = str(load_anchor_config().get("memory_home", "")).strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def persist_anchor(memory_home: Path) -> None:
    """Write fixed anchor — only memory_home (survives bundle updates)."""
    ANCHOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = load_anchor_config()
    if not isinstance(data, dict):
        data = {}
    data["memory_home"] = str(memory_home.expanduser().resolve())
    ANCHOR_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def detect_plugin_root(start: str | Path | None = None) -> Path | None:
    """
    Walk parents from start until .cursor-plugin/plugin.json + INSTRUCTIONS.md.
    Location-agnostic (plugins/local, official path, git dev tree).
    """
    if start is None:
        return None
    cur = Path(start).resolve()
    if cur.is_file():
        cur = cur.parent
    for _ in range(16):
        manifest = cur / PLUGIN_MANIFEST
        if manifest.is_file() and (cur / "INSTRUCTIONS.md").is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return _detect_legacy_framework_root(start)


def _detect_legacy_framework_root(script_file: str | Path) -> Path | None:
    """Pre-plugin layouts: script under scripts/ → parent with INSTRUCTIONS.md."""
    scripts = Path(script_file).resolve().parent
    if scripts.name == "scripts":
        candidate = scripts.parent
        if (candidate / "INSTRUCTIONS.md").is_file():
            return candidate
    if (scripts / "INSTRUCTIONS.md").is_file():
        return scripts
    return None


def resolve_plugin_root(
    override: str | None = None,
    *,
    script_file: str | Path | None = None,
    memory_home: Path | None = None,
) -> Path | None:
    """Plugin bundle root (replaceable code)."""
    found = _valid_plugin_dir(override or "")
    if found:
        return found
    for key in ("AGENT_MEMORY_FRAMEWORK", "FRAMEWORK_ROOT", "AGENT_MEMORY_INSTALL"):
        found = _valid_plugin_dir(os.environ.get(key, "").strip())
        if found:
            return found
    hook = _load_legacy_hook_env()
    found = _valid_plugin_dir(hook.get("AGENT_MEMORY_FRAMEWORK", ""))
    if found:
        return found
    if memory_home is not None:
        hub_cfg = load_hub_config(memory_home)
        found = _valid_plugin_dir(str(hub_cfg.get("plugin_root", "")).strip())
        if found:
            return found
        found = _valid_plugin_dir(str(hub_cfg.get("framework_root", "")).strip())
        if found:
            return found
    if script_file is not None:
        detected = detect_plugin_root(script_file)
        if detected is not None:
            return detected
    return None


# Back-compat alias used across scripts
resolve_framework_root = resolve_plugin_root


def resolve_memory_home(
    override: str | None = None,
    script_file: str | Path | None = None,
) -> Path:
    """
    CLI > env MEMORY_HOME > anchor > default ~/.cursor/agent-memory/
    Hub is always outside the plugin bundle.
    """
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("MEMORY_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    anchored = memory_home_from_anchor()
    if anchored is not None:
        return anchored.expanduser().resolve()
    legacy_hook = _load_legacy_hook_env()
    hook_hub = legacy_hook.get("MEMORY_HOME", "").strip()
    if hook_hub:
        warnings.warn(
            "MEMORY_HOME from legacy ~/.cursor/hooks/agent-memory.env is deprecated; "
            "use anchor ~/.cursor/agent-memory/config.json",
            DeprecationWarning,
            stacklevel=2,
        )
        return Path(hook_hub).expanduser().resolve()
    if ANCHOR_FILE.is_file():
        return DEFAULT_MEMORY_HOME.resolve()
    legacy = _read_json(LEGACY_GLOBAL_CONFIG)
    legacy_hub = legacy.get("memory_home", "").strip()
    if legacy_hub:
        warnings.warn(
            "Reading memory_home from legacy XDG config is deprecated; "
            "use ~/.cursor/agent-memory/config.json anchor",
            DeprecationWarning,
            stacklevel=2,
        )
        return Path(legacy_hub).expanduser().resolve()
    return DEFAULT_MEMORY_HOME.resolve()


def load_hub_config(memory_home: Path) -> dict:
    return _read_json(memory_home / "config.json")


def _valid_plugin_dir(path: str) -> Path | None:
    if not path or not isinstance(path, str):
        return None
    p = Path(path).expanduser()
    if not p.is_dir():
        return None
    if (p / "INSTRUCTIONS.md").is_file():
        return p.resolve()
    if (p / PLUGIN_MANIFEST).is_file():
        return p.resolve()
    return None


def persist_hub_config(
    plugin_root: Path,
    memory_home: Path,
) -> None:
    """Hub-local config (plugin path + memory path)."""
    root_str = str(plugin_root.resolve())
    hub_str = str(memory_home.resolve())
    hub_cfg_path = memory_home / "config.json"
    hub_cfg = load_hub_config(memory_home)
    if not isinstance(hub_cfg, dict):
        hub_cfg = {}
    changed = False
    for key, val in (
        ("plugin_root", root_str),
        ("framework_root", root_str),
        ("memory_home", hub_str),
    ):
        if hub_cfg.get(key) != val:
            hub_cfg[key] = val
            changed = True
    # Strip removed concepts from older hub configs (not part of current model).
    for legacy_key in ("install_root", "dev_root", "handoff_mode"):
        if legacy_key in hub_cfg:
            del hub_cfg[legacy_key]
            changed = True
    if changed:
        memory_home.mkdir(parents=True, exist_ok=True)
        hub_cfg_path.write_text(
            json.dumps(hub_cfg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def persist_paths(
    plugin_root: Path,
    memory_home: Path,
) -> None:
    """Anchor + hub config (idempotent)."""
    persist_anchor(memory_home)
    persist_hub_config(plugin_root, memory_home)


def persist_framework_root(
    framework_root: Path,
    *,
    memory_home: Path | None = None,
    update_global: bool = False,
    update_hub: bool = True,
    **_: object,
) -> None:
    if update_global:
        raise ValueError("update_global is disabled")
    if update_hub and memory_home is not None:
        persist_paths(framework_root.resolve(), memory_home.resolve())


def framework_version(plugin_root: Path | None) -> str | None:
    if not plugin_root:
        return None
    version_file = plugin_root / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return None


# Removed: framework_root_from_memory_home, default_memory_home, load_global_config
