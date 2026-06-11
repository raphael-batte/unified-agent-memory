"""Delete stale hub artifacts for already-processed chats."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from lib.chats_manifest import load_manifest, processed_by_id
from lib.defaults import HUB_RETENTION_DAYS

_UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
_STAGING_SUFFIX_RE = re.compile(r"-([0-9a-f]{8})\.md$", re.I)


def _chat_id_from_name(name: str) -> str | None:
    if name.endswith(".json"):
        return Path(name).stem
    match = _STAGING_SUFFIX_RE.search(name)
    if match:
        return match.group(1)
    match = _UUID_RE.search(name)
    if match:
        return match.group(1)
    return None


def _is_stale(path: Path, *, cutoff: datetime) -> bool:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return False
    return mtime < cutoff


def cleanup_hub_artifacts(
    memory_home: Path,
    *,
    retention_days: int = HUB_RETENTION_DAYS,
    dry_run: bool = True,
) -> dict:
    """
    Remove old merge-staging and extracts for chats already in manifest.processed.
  Never deletes artifacts for unprocessed chat ids.
    """
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    processed_ids = set(processed_by_id(manifest))
    cutoff = datetime.now() - timedelta(days=retention_days)
    stats = {
        "retention_days": retention_days,
        "dry_run": dry_run,
        "deleted": 0,
        "would_delete": 0,
        "skipped_unprocessed": 0,
        "skipped_fresh": 0,
        "paths": [],
    }

    scan_dirs = [
        memory_home / "chats" / "merge-staging",
        memory_home / "chats" / "extracts",
    ]
    for root in scan_dirs:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if not path.is_file():
                continue
            chat_id = _chat_id_from_name(path.name)
            if not chat_id or chat_id not in processed_ids:
                stats["skipped_unprocessed"] += 1
                continue
            if not _is_stale(path, cutoff=cutoff):
                stats["skipped_fresh"] += 1
                continue
            rel = str(path.relative_to(memory_home))
            stats["paths"].append(rel)
            if dry_run:
                stats["would_delete"] += 1
            else:
                try:
                    path.unlink()
                    stats["deleted"] += 1
                except OSError:
                    pass
    return stats
