"""Repair [extracted] Decisions whose head was cut off by a mid-word cue match.

Before v0.29.7 a learned commitment prefix such as a one-letter function word
could match inside the first word of a message (or strip a leading function
word), and the extractor kept only the text after it. The damage is
recognisable without guessing: near the start of a source user message the
bullet's text follows a word character, or nothing but function words.

Only those bullets are touched. Each is rebuilt from its full source message by
the current extractor, or dropped when that message no longer yields a
Decision. Bullets that match cleanly, or whose source cannot be found, stay.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.chats_manifest import load_manifest
from lib.decision_extract import extract_decision_candidates
from lib.defaults import DECISION_COMMITMENT_CUE_MAX_START
from lib.hub_lock import hub_lock, write_atomic
from lib.lang_learn import is_weak_learned_phrase
from lib.secrets_guard import sanitize_message
from lib.transcript import find_transcript
from lib.transcript_parse import parse_transcript

EXTRACTED_PREFIX = "- [extracted]"
_NORM_RE = re.compile(r"\s+")
_WORD_CHAR_RE = re.compile(r"\w")
#: Long enough to pin one message, short enough to survive the extractor's trim.
_PROBE_LEN = 60
#: The bug only cut at a cue found near the start: window + the longest learned phrase.
_MAX_CUT_OFFSET = DECISION_COMMITMENT_CUE_MAX_START + 64


@dataclass
class Repair:
    path: Path
    old: str
    new: str | None  # None = drop the bullet


def _norm(text: str) -> str:
    return _NORM_RE.sub(" ", text).strip()


def _bullet_probe(line: str) -> str:
    text = line.strip()[len(EXTRACTED_PREFIX) :].strip()
    if text.endswith("..."):
        text = text[:-3].rstrip()
    return _norm(text)[:_PROBE_LEN]


def _decision_files(memory_home: Path) -> list[tuple[Path, str]]:
    chats = memory_home / "chats"
    out = [(p, p.stem) for p in sorted((chats / "projects").glob("*.md"))]
    out += [
        (p, p.stem.removesuffix("-decisions"))
        for p in sorted((chats / "archive").glob("*-decisions.md"))
    ]
    return out


def _chats_by_slug(memory_home: Path) -> dict[str, list[str]]:
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    out: dict[str, list[str]] = {}
    for entry in manifest.get("processed") or []:
        chat_id = str(entry.get("id") or "")
        for target in entry.get("distilled_to") or []:
            out.setdefault(Path(str(target)).stem.lower(), []).append(chat_id)
    return out


class _SourceIndex:
    def __init__(self, memory_home: Path) -> None:
        self.memory_home = memory_home
        self._cache: dict[str, list[str]] = {}

    def messages(self, chat_ids: list[str]) -> list[str]:
        out: list[str] = []
        for chat_id in chat_ids:
            if chat_id not in self._cache:
                self._cache[chat_id] = self._load(chat_id)
            out.extend(self._cache[chat_id])
        return out

    def _load(self, chat_id: str) -> list[str]:
        path = find_transcript(chat_id, memory_home=self.memory_home)
        if path is None:
            return []
        try:
            return [_norm(t) for t in parse_transcript(path).user_texts() if t.strip()]
        except Exception:
            return []


def _cut_here(msg: str, start: int) -> bool:
    """Mid-word, or after nothing but function words (``po suti`` -> ``suti``)."""
    if _WORD_CHAR_RE.match(msg[start - 1]):
        return True
    head = msg[:start].rstrip(" ,:;-")
    return bool(head) and is_weak_learned_phrase(head)


def _truncated_source(probe: str, messages: list[str]) -> str | None:
    """Source message when the probe only ever appears cut off, else None."""
    if not probe:
        return None
    best: tuple[int, str] | None = None
    for msg in messages:
        start = msg.find(probe)
        while start >= 0:
            # A pasted hub excerpt quotes the damaged bullet itself — not a source.
            if msg[:start].rstrip().endswith("[extracted]"):
                pass
            elif start == 0:
                return None  # the bullet starts where the message does — fine
            elif start <= _MAX_CUT_OFFSET and _cut_here(msg, start):
                if best is None or start < best[0]:
                    best = (start, msg)
            elif not _WORD_CHAR_RE.match(msg[start - 1]):
                return None  # a clean occurrence exists — the bullet is fine
            start = msg.find(probe, start + 1)
    return best[1] if best else None


def _rebuild(source: str, memory_home: Path) -> str | None:
    clean, _n = sanitize_message(source)
    if clean is None:
        return None
    candidates, _stats = extract_decision_candidates([clean], memory_home=memory_home)
    if not candidates:
        return None
    return f"{EXTRACTED_PREFIX} {candidates[0]['text']}"


def find_repairs(memory_home: Path) -> tuple[list[Repair], dict[str, int]]:
    by_slug = _chats_by_slug(memory_home)
    # Renamed workspaces and imported archives distill under another slug.
    all_chats = sorted({cid for ids in by_slug.values() for cid in ids})
    index = _SourceIndex(memory_home)
    repairs: list[Repair] = []
    stats = {"bullets": 0, "truncated": 0, "rebuilt": 0, "dropped": 0, "untraced": 0}
    for path, slug in _decision_files(memory_home):
        lines = path.read_text(encoding="utf-8").splitlines()
        bullets = [ln for ln in lines if ln.strip().startswith(EXTRACTED_PREFIX)]
        if not bullets:
            continue
        messages = index.messages(by_slug.get(slug.lower(), []))
        present = {ln.strip() for ln in lines}
        for line in bullets:
            stats["bullets"] += 1
            probe = _bullet_probe(line)
            pool = messages
            if not any(probe in m for m in pool):
                pool = index.messages(all_chats)
                if not any(probe in m for m in pool):
                    stats["untraced"] += 1
                    continue
            source = _truncated_source(probe, pool)
            if source is None:
                continue
            new = _rebuild(source, memory_home)
            if new is not None and new.strip() == line.strip():
                continue  # a legitimate cue strip the extractor still makes
            if new is not None and new in present:
                new = None  # the full version is already in the file
            stats["truncated"] += 1
            stats["rebuilt" if new else "dropped"] += 1
            if new:
                present.add(new)
            repairs.append(Repair(path=path, old=line, new=new))
    return repairs, stats


def apply_repairs(memory_home: Path, repairs: list[Repair]) -> dict[str, Any]:
    """Rewrite affected files under the hub lock; originals go to a backup dir."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # projects-backup-* is skipped by hub search, so the snapshot never ranks.
    backup_root = memory_home / "chats" / f"projects-backup-repair-{stamp}"
    by_path: dict[Path, list[Repair]] = {}
    for rep in repairs:
        by_path.setdefault(rep.path, []).append(rep)

    with hub_lock(memory_home, owner="doctor-repair"):
        for path, reps in by_path.items():
            rel = path.relative_to(memory_home / "chats")
            backup = backup_root / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)

            swap = {rep.old: rep.new for rep in reps}
            out: list[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line in swap:
                    if swap[line] is not None:
                        indent = line[: len(line) - len(line.lstrip())]
                        out.append(indent + swap[line])
                    continue
                out.append(line)
            write_atomic(path, "\n".join(out) + "\n")
    return {"files": len(by_path), "backup": str(backup_root)}
