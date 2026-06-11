"""Query expansion synonyms for hub search (templates/lang + hub override)."""

from __future__ import annotations

import json
from pathlib import Path

from lib.lang_cues import _plugin_lang_dir
from lib.memory_config import detect_plugin_root, load_hub_config

_MAX_GROUPS = 40
_MAX_TERM_LEN = 32
_PREFIX_LEN = 4


def _normalize_term(item: str) -> str | None:
    t = item.strip().lower()
    if not t or len(t) > _MAX_TERM_LEN:
        return None
    return t


def _prefix_key(token: str) -> str:
    return token[:_PREFIX_LEN] if len(token) >= _PREFIX_LEN else token


def _parse_synonym_groups(raw_groups: object) -> list[list[str]]:
    if not isinstance(raw_groups, list):
        return []
    out: list[list[str]] = []
    for group in raw_groups[:_MAX_GROUPS]:
        if not isinstance(group, list):
            continue
        terms: list[str] = []
        for item in group:
            if not isinstance(item, str):
                continue
            norm = _normalize_term(item)
            if norm and norm not in terms:
                terms.append(norm)
        if len(terms) >= 2:
            out.append(terms)
    return out


def load_search_synonyms(
    *,
    memory_home: Path | None = None,
    plugin_root: Path | None = None,
) -> list[list[str]]:
    groups: list[list[str]] = []
    lang_dir = _plugin_lang_dir(plugin_root or detect_plugin_root(Path(__file__)))
    if lang_dir is not None:
        for path in sorted(lang_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(raw, dict):
                groups.extend(_parse_synonym_groups(raw.get("search_synonyms")))

    if memory_home is not None:
        hub = load_hub_config(memory_home)
        custom = hub.get("lang")
        if isinstance(custom, dict):
            groups.extend(_parse_synonym_groups(custom.get("search_synonyms")))

    return groups


def _token_matches_group(token: str, group: list[str]) -> bool:
    for term in group:
        n = min(len(token), len(term), _PREFIX_LEN)
        if n >= 3 and token[:n] == term[:n]:
            return True
        if token in term or term in token:
            return True
    return False


def expand_query_tokens(tokens: list[str], synonym_groups: list[list[str]]) -> list[str]:
    expanded = list(tokens)
    seen = set(expanded)
    for tok in tokens:
        for group in synonym_groups:
            if not _token_matches_group(tok, group):
                continue
            for term in group:
                key = _prefix_key(term)
                if key not in seen:
                    expanded.append(key)
                    seen.add(key)
    return expanded
