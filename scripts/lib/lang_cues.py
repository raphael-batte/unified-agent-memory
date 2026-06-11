"""Load cue-word lists from templates/lang/*.json with optional hub override."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.distill_metrics import append_metric
from lib.memory_config import detect_plugin_root, load_hub_config

_MAX_PHRASE_LEN = 64
_MAX_LIST_LEN = 100

_LANG_KEYS = (
    "next_step_markers",
    "list_intro_words",
    "recommend_stems",
    "recommend_actions",
    "continue_phrases",
    "commitment_prefixes",
    "new_task_cues",
    "correction_cues",
    "action_verbs",
)

_CACHE: dict[str, dict[str, list[str]]] = {}


def clear_lang_cue_cache() -> None:
    _CACHE.clear()


def _plugin_lang_dir(plugin_root: Path | None) -> Path | None:
    if plugin_root is None:
        plugin_root = detect_plugin_root(Path(__file__))
    if plugin_root is None:
        return None
    lang_dir = plugin_root / "templates" / "lang"
    return lang_dir if lang_dir.is_dir() else None


def _validate_phrase(item: Any) -> str | None:
    if not isinstance(item, str):
        return None
    text = item.strip()
    if not text or len(text) > _MAX_PHRASE_LEN:
        return None
    return text


def _load_json_file(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {key: [] for key in _LANG_KEYS}
    if not path.is_file():
        return out
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return out
    if not isinstance(raw, dict):
        return out
    for key in _LANG_KEYS:
        values = raw.get(key)
        if not isinstance(values, list):
            continue
        cleaned: list[str] = []
        for item in values[:_MAX_LIST_LEN]:
            phrase = _validate_phrase(item)
            if phrase:
                cleaned.append(phrase)
        out[key] = cleaned
    return out


def _merge_lang_dicts(base: dict[str, list[str]], extra: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {key: list(base.get(key) or []) for key in _LANG_KEYS}
    for key in _LANG_KEYS:
        for phrase in extra.get(key) or []:
            if phrase not in merged[key]:
                merged[key].append(phrase)
    return merged


def load_lang_cues(
    *,
    memory_home: Path | None = None,
    plugin_root: Path | None = None,
) -> dict[str, list[str]]:
    cache_key = f"{memory_home}:{plugin_root}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    lang_dir = _plugin_lang_dir(plugin_root)
    merged: dict[str, list[str]] = {key: [] for key in _LANG_KEYS}
    if lang_dir is not None:
        for path in sorted(lang_dir.glob("*.json")):
            merged = _merge_lang_dicts(merged, _load_json_file(path))

    if memory_home is not None:
        hub = load_hub_config(memory_home)
        custom = hub.get("lang")
        if isinstance(custom, dict):
            custom_clean: dict[str, list[str]] = {key: [] for key in _LANG_KEYS}
            invalid = False
            for key in _LANG_KEYS:
                values = custom.get(key)
                if values is None:
                    continue
                if not isinstance(values, list):
                    invalid = True
                    break
                for item in values[:_MAX_LIST_LEN]:
                    phrase = _validate_phrase(item)
                    if phrase is None and item not in (None, ""):
                        invalid = True
                        break
                    if phrase:
                        custom_clean[key].append(phrase)
                if invalid:
                    break
            else:
                merged = _merge_lang_dicts(merged, custom_clean)
            if invalid:
                append_metric(
                    memory_home,
                    {"event": "lang_config_invalid", "detail": "hub config.lang rejected"},
                )

    _CACHE[cache_key] = merged
    return merged


def phrase_alt(phrases: list[str]) -> str:
    parts = [re.escape(p) for p in phrases if p]
    return "|".join(parts)


def build_correction_pattern(cues: dict[str, list[str]]) -> re.Pattern[str]:
    en = [
        "don't",
        "do not",
        "instead",
        "wrong",
        "fix",
        "broken",
        "regression",
        "revert",
        "not working",
    ]
    merged = list(dict.fromkeys(en + list(cues.get("correction_cues") or [])))
    return re.compile(r"(?:%s)" % phrase_alt(merged), re.I)


def build_new_task_pattern(cues: dict[str, list[str]]) -> re.Pattern[str]:
    en = ["new task", "different topic", "switching to", "let's move on", "lets move on"]
    merged = list(dict.fromkeys(en + list(cues.get("new_task_cues") or [])))
    return re.compile(r"(?:^|\b)(?:%s)\b" % phrase_alt(merged), re.I)


def build_action_pattern(cues: dict[str, list[str]]) -> re.Pattern[str]:
    en = [
        r"\bcd\s+",
        r"\bnpm\s+",
        r"\bpython3?\s+",
        r"\bbash\s+",
        r"\./scripts/",
        r"\bdeploy\b",
        r"\bcommit\b",
        r"\bflutter\s+",
        r"\brun\s+",
        r"device\s+QA",
    ]
    extra = [re.escape(p) for p in cues.get("action_verbs") or []]
    body = "|".join(en + extra)
    return re.compile(r"(?:%s)" % body, re.I)


def build_line_patterns(cues: dict[str, list[str]]) -> list[re.Pattern[str]]:
    markers = list(cues.get("next_step_markers") or ["next step", "next steps"])
    if "next step" not in [m.lower() for m in markers]:
        markers = ["next step", "next steps", *markers]
    marker_alt = phrase_alt(markers)
    list_words = phrase_alt(cues.get("list_intro_words") or ["next"])
    stems = phrase_alt(cues.get("recommend_stems") or [])
    actions = phrase_alt(cues.get("recommend_actions") or [])
    cont = phrase_alt(cues.get("continue_phrases") or ["if you want to continue", "to continue", "start with"])

    patterns: list[re.Pattern[str]] = [
        re.compile(
            rf"(?:{marker_alt})\s*[:—\-]\s*(.+)",
            re.I | re.S,
        ),
    ]
    if list_words:
        patterns.append(
            re.compile(
                rf"(?:^|\n)\s*(?:\d+\.|[-*•])\s*(?:{list_words})\s*[:—\-]?\s*(.+)",
                re.I | re.S,
            )
        )
    if stems and actions:
        patterns.append(
            re.compile(
                rf"(?:{stems})\s+(?:{actions})\s*[:\-]?\s*(.+)",
                re.I | re.S,
            )
        )
    if cont:
        patterns.append(
            re.compile(rf"(?:{cont})\s*[:—\-]?\s*(.+)", re.I | re.S),
        )
    return patterns


def build_commitment_pattern(cues: dict[str, list[str]]) -> re.Pattern[str]:
    en = [
        r"ok(?:ay)?\s*,?\s*(?:then\s+)?",
        r"(?:let's|lets)\s+(?:do|start)\s+",
        r"go\s+with\s+",
    ]
    extra = [re.escape(p) + r"\s*,?\s*" for p in cues.get("commitment_prefixes") or []]
    body = "|".join(en + extra)
    return re.compile(rf"(?:^|\b)(?:{body})\s*(.+)", re.I | re.S)
