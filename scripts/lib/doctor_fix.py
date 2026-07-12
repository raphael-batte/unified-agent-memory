"""memory-doctor --fix: align anchor + hub config."""

from __future__ import annotations

from pathlib import Path

from lib.defaults import HUB_RETENTION_DAYS, load_thresholds
from lib.hub_retention import cleanup_hub_artifacts
from lib.memory_config import (
    anchor_points_to_initialized_hub,
    load_hub_config,
    persist_paths,
)

SCRIPT_DIR = Path(__file__).resolve().parents[1]


def run_fix(
    *,
    memory_home: Path,
    framework_root: Path,
    dry_run: bool = False,
    memory_home_cli: bool = False,
) -> dict:
    actions: list[str] = []
    errors: list[str] = []

    fw_str = str(framework_root.resolve())
    target_hub = memory_home.resolve()
    if not memory_home_cli:
        preserved = anchor_points_to_initialized_hub()
        if preserved is not None and preserved != target_hub:
            target_hub = preserved
            actions.append(f"preserved anchor memory_home → {target_hub}")
    hub_str = str(target_hub)
    if not dry_run:
        persist_paths(framework_root.resolve(), target_hub)
        actions.append(
            f"set anchor + hub config → plugin_root={fw_str}, memory_home={hub_str}"
        )
    else:
        actions.append(f"would set anchor + hub → plugin_root={fw_str}")

    actions.append(
        "plugin install: bash scripts/install-local.sh links bundle + ~/.cursor/skills/; "
        "remove legacy agent-memory entries from ~/.cursor/hooks.json if present"
    )

    legacy_link = SCRIPT_DIR / "link-cursor-skills.sh"
    if legacy_link.is_file():
        actions.append(
            "legacy link-cursor-skills.sh not run — plugin provides skills via bundle"
        )

    hub_cfg = load_hub_config(target_hub)
    retention_days = int(
        load_thresholds(hub_cfg).get("retention_days", HUB_RETENTION_DAYS)
    )
    retention = cleanup_hub_artifacts(
        target_hub, retention_days=retention_days, dry_run=dry_run
    )
    if retention["would_delete"] or retention["deleted"]:
        verb = "would delete" if dry_run else "deleted"
        count = retention["would_delete"] if dry_run else retention["deleted"]
        actions.append(
            f"{verb} {count} stale staging/extract file(s) "
            f"(>{retention_days}d, processed chats only)"
        )

    return {
        "actions": actions,
        "errors": errors,
        "ok": not errors,
        "dry_run": dry_run,
    }
