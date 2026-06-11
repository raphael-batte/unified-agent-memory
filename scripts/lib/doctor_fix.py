"""memory-doctor --fix: align anchor + hub config."""

from __future__ import annotations

from pathlib import Path

from lib.defaults import HUB_RETENTION_DAYS, load_thresholds
from lib.hub_retention import cleanup_hub_artifacts
from lib.memory_config import load_hub_config, persist_paths

SCRIPT_DIR = Path(__file__).resolve().parents[1]


def run_fix(
    *,
    memory_home: Path,
    framework_root: Path,
    dry_run: bool = False,
) -> dict:
    actions: list[str] = []
    errors: list[str] = []

    fw_str = str(framework_root.resolve())
    hub_str = str(memory_home.resolve())
    if not dry_run:
        persist_paths(framework_root.resolve(), memory_home.resolve())
        actions.append(
            f"set anchor + hub config → plugin_root={fw_str}, memory_home={hub_str}"
        )
    else:
        actions.append(f"would set anchor + hub → plugin_root={fw_str}")

    actions.append(
        "if using plugin: remove legacy ~/.cursor/hooks.json agent-memory entries "
        "and ~/.cursor/skills/agent-memory symlink to avoid double distill"
    )

    legacy_link = SCRIPT_DIR / "link-cursor-skills.sh"
    if legacy_link.is_file():
        actions.append(
            "legacy link-cursor-skills.sh not run — plugin provides skills via bundle"
        )

    hub_cfg = load_hub_config(memory_home)
    retention_days = int(
        load_thresholds(hub_cfg).get("retention_days", HUB_RETENTION_DAYS)
    )
    retention = cleanup_hub_artifacts(
        memory_home, retention_days=retention_days, dry_run=dry_run
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
