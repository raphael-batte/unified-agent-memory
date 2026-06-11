"""Extract forward pointer (## Next step) from transcript tail."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lib.lang_cues import (
    build_action_pattern,
    build_commitment_pattern,
    build_line_patterns,
    load_lang_cues,
)
from lib.secrets_guard import is_terminal_noise, sanitize_message
from lib.agent_live_distill_constants import (
    AGENT_LIVE_CONFIDENCE,
    AGENT_LIVE_POINTER_SOURCE,
)
from lib.structured_signals import (
    TODO_POINTER_CONFIDENCE,
    TODO_POINTER_SOURCE,
    todo_pointer_from_extract,
    todo_pointer_from_parsed,
)
from lib.transcript_cursor import normalize_user_text
from lib.transcript_parse import parse_transcript

MAX_POINTER_LEN = 240
MIN_POINTER_LEN = 12

NO_POINTER_MARKER = "_No forward pointer._"
STALE_POINTER_PREFIX = "[?]"

_SOURCE_CONFIDENCE: dict[str, float] = {
    AGENT_LIVE_POINTER_SOURCE: AGENT_LIVE_CONFIDENCE,
    "user_commitment": 0.95,
    "todo_state": TODO_POINTER_CONFIDENCE,
    "user_pattern": 0.85,
    "assistant_pattern": 0.55,
    "assistant_pattern_weak": 0.45,
    "assistant_action": 0.45,
    "extract_fallback": 0.55,
    "none": 0.0,
}

_PATTERN_CACHE: dict[str, tuple[list[re.Pattern[str]], re.Pattern[str], re.Pattern[str]]] = {}


@dataclass(frozen=True)
class PointerResult:
    text: str | None
    confidence: float
    source: str

    @property
    def is_low_confidence(self) -> bool:
        from lib.defaults import POINTER_LOW_CONFIDENCE

        return self.text is None or self.confidence < POINTER_LOW_CONFIDENCE


def clear_pointer_pattern_cache() -> None:
    _PATTERN_CACHE.clear()


def _resolve_memory_home(extract: dict, memory_home: Path | None) -> Path | None:
    if memory_home is not None:
        return memory_home
    raw = extract.get("memory_home")
    if raw:
        return Path(str(raw)).expanduser()
    return None


def _patterns_for(memory_home: Path | None = None) -> tuple[
    list[re.Pattern[str]], re.Pattern[str], re.Pattern[str]
]:
    key = str(memory_home or "")
    if key not in _PATTERN_CACHE:
        cues = load_lang_cues(memory_home=memory_home)
        _PATTERN_CACHE[key] = (
            build_line_patterns(cues),
            build_commitment_pattern(cues),
            build_action_pattern(cues),
        )
    return _PATTERN_CACHE[key]


def _clean_candidate(text: str) -> str | None:
    line = re.sub(r"\s+", " ", text.strip())
    line = re.sub(r"^[-*•]\s+", "", line)
    if len(line) < MIN_POINTER_LEN:
        return None
    if len(line) > MAX_POINTER_LEN:
        line = line[: MAX_POINTER_LEN - 3].rstrip() + "..."
    clean, _n = sanitize_message(line)
    if not clean:
        return None
    return clean


def _match_patterns(blob: str, *, memory_home: Path | None = None) -> str | None:
    line_pats, _, _ = _patterns_for(memory_home)
    for pat in line_pats:
        m = pat.search(blob)
        if m:
            cand = _clean_candidate(m.group(1).split("\n")[0])
            if cand:
                return cand
    return None


def _match_commitment(blob: str, *, memory_home: Path | None = None) -> str | None:
    _, commitment_pat, _ = _patterns_for(memory_home)
    m = commitment_pat.search(blob)
    if not m:
        return None
    return _clean_candidate(m.group(1).split("\n")[0])


def _try_user_text(blob: str, *, memory_home: Path | None = None) -> tuple[str | None, str]:
    norm = normalize_user_text(blob).strip()
    if not norm or is_terminal_noise(norm):
        return None, "none"
    hit = _match_commitment(norm, memory_home=memory_home)
    if hit:
        return hit, "user_commitment"
    hit = _match_patterns(norm, memory_home=memory_home)
    if hit:
        return hit, "user_pattern"
    _, _, action_pat = _patterns_for(memory_home)
    if "?" not in norm and action_pat.search(norm):
        cand = _clean_candidate(norm)
        if cand:
            return cand, "user_pattern"
    return None, "none"


def _user_tail_from_extract(extract: dict, *, n: int = 3) -> list[str]:
    msgs = extract.get("user_messages") or []
    return [m for m in msgs[-n:] if isinstance(m, str) and m.strip()]


def extract_forward_pointer_result(
    extract: dict,
    *,
    memory_home: Path | None = None,
) -> PointerResult:
    """
    Heuristic next-step from transcript tail with confidence tier.
    Priority: last raw user (commitment) → user patterns → assistant patterns
    → extract user fallback → assistant action-hint (lowest).
    """
    hub = _resolve_memory_home(extract, memory_home)
    agent_live = extract.get("agent_live") or {}
    live_next = agent_live.get("next_step")
    if isinstance(live_next, str) and live_next.strip():
        cand = _clean_candidate(live_next.strip())
        if cand:
            return PointerResult(
                cand,
                _SOURCE_CONFIDENCE[AGENT_LIVE_POINTER_SOURCE],
                AGENT_LIVE_POINTER_SOURCE,
            )

    source = extract.get("source_path")
    jsonl = Path(str(source)).expanduser() if source else None

    if jsonl and jsonl.is_file():
        parsed = parse_transcript(jsonl)
        last_user = parsed.last_user_text()
        if last_user:
            hit, tier = _try_user_text(last_user, memory_home=hub)
            if hit:
                return PointerResult(hit, _SOURCE_CONFIDENCE[tier], tier)

        todo_signal = todo_pointer_from_parsed(parsed)
        if todo_signal:
            return PointerResult(
                todo_signal.text,
                todo_signal.confidence,
                TODO_POINTER_SOURCE,
            )

        for blob in reversed(parsed.assistant_text_tail()):
            hit = _match_patterns(blob, memory_home=hub)
            if hit:
                tier = "assistant_pattern"
                if last_user and "?" in last_user:
                    tier = "assistant_pattern_weak"
                return PointerResult(hit, _SOURCE_CONFIDENCE[tier], tier)

        for blob in reversed(parsed.assistant_text_tail()):
            paras = [p.strip() for p in blob.split("\n\n") if p.strip()]
            if not paras:
                continue
            last = paras[-1]
            _, _, action_pat = _patterns_for(hub)
            if action_pat.search(last):
                cand = _clean_candidate(last.split("\n")[0])
                if cand:
                    return PointerResult(
                        cand,
                        _SOURCE_CONFIDENCE["assistant_action"],
                        "assistant_action",
                    )

    todo_signal = todo_pointer_from_extract(extract)
    if todo_signal:
        return PointerResult(
            todo_signal.text,
            todo_signal.confidence,
            TODO_POINTER_SOURCE,
        )

    for msg in reversed(_user_tail_from_extract(extract)):
        hit, tier = _try_user_text(msg, memory_home=hub)
        if hit:
            conf = _SOURCE_CONFIDENCE.get(
                "extract_fallback" if tier == "user_pattern" else tier,
                _SOURCE_CONFIDENCE["extract_fallback"],
            )
            src = "extract_fallback" if tier == "user_pattern" else tier
            return PointerResult(hit, conf, src)

    return PointerResult(None, _SOURCE_CONFIDENCE["none"], "none")


def extract_forward_pointer(
    extract: dict,
    *,
    memory_home: Path | None = None,
) -> str | None:
    return extract_forward_pointer_result(extract, memory_home=memory_home).text
