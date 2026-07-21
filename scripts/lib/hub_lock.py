"""Cross-environment hub lock.

The hub is shared by environments with different trigger mechanisms: Cursor syncs from a
2-hourly launchd job, Claude Code writes from event hooks. Both can touch
``chats/projects/*.md`` and ``chats/manifest.json`` at the same time.

Cursor's cron script already guards itself with a ``mkdir`` lock at
``$MEMORY_HOME/.state/periodic-sync.lock``. We adopt *that same* lock rather than invent a
second protocol — the cron path stays untouched and simply keeps working.

``mkdir`` is atomic on POSIX, so it doubles as a mutex. A holder that dies without cleaning
up would wedge the hub forever, hence the staleness cutoff.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

#: Same name the Cursor cron script uses — do not rename.
LOCK_NAME = "periodic-sync.lock"

#: A lock older than this is assumed abandoned (crash, SIGKILL) and taken over.
STALE_AFTER_SECONDS = 15 * 60

#: Hooks run inside an interactive session — never block the user for long.
DEFAULT_TIMEOUT_SECONDS = 5.0

_POLL_INTERVAL = 0.05


class HubBusy(RuntimeError):
    """Raised when the hub lock could not be acquired within the timeout."""


def lock_path(memory_home: Path) -> Path:
    return memory_home / ".state" / LOCK_NAME


def _is_stale(path: Path, *, stale_after: float) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age > stale_after


def _try_acquire(path: Path, *, owner: str) -> bool:
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        return False
    except OSError:
        return False
    # Best effort breadcrumb; the lock itself is the directory, not this file.
    try:
        (path / "owner.json").write_text(
            json.dumps({"owner": owner, "pid": os.getpid(), "ts": time.time()}) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return True


def _release(path: Path) -> None:
    try:
        for child in path.iterdir():
            child.unlink(missing_ok=True)
        path.rmdir()
    except OSError:
        pass


@contextmanager
def hub_lock(
    memory_home: Path,
    *,
    owner: str = "hook",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    stale_after: float = STALE_AFTER_SECONDS,
) -> Iterator[Path]:
    """Hold the shared hub lock, or raise :class:`HubBusy`.

    Callers that must not block the user should catch ``HubBusy`` and fall back to
    staging-only work, leaving the durable write to the next trigger.
    """
    path = lock_path(memory_home)
    deadline = time.monotonic() + max(0.0, timeout)

    while True:
        if _try_acquire(path, owner=owner):
            break
        if _is_stale(path, stale_after=stale_after):
            _release(path)
            if _try_acquire(path, owner=owner):
                break
        if time.monotonic() >= deadline:
            raise HubBusy(f"hub lock held by another process: {path}")
        time.sleep(_POLL_INTERVAL)

    try:
        yield path
    finally:
        _release(path)


def write_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write via temp file + ``os.replace`` so a concurrent reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_json_atomic(path: Path, data: Any, *, indent: int = 2) -> None:
    write_atomic(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")
