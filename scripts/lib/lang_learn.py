"""Mine user lang cues from transcripts; persist lang_learned.json in hub."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.defaults import DOMAIN_STOPWORDS, GENERIC_MESSAGE_START
from lib.distill_metrics import append_metric
from lib.lang_actionability import is_generic_only, is_pointer_actionable
from lib.lang_cues import clear_lang_cue_cache, load_lang_cues
from lib.forward_pointer import (
    clear_pointer_pattern_cache,
    score_extract_with_learned_projection,
)
from lib.secrets_guard import is_terminal_noise, sanitize_message
from lib.transcript_cursor import TranscriptSchemaError
from lib.topic_segmentation import clear_new_task_cache
from lib.transcript_cursor import normalize_user_text
from lib.transcript_parse import ParsedTranscript, parse_transcript

LANG_LEARNED_FILE = "lang_learned.json"
LEARNED_VERSION = 1
MIN_COUNT_DEFAULT = 2
MIN_DISTINCT_CHATS_DEFAULT = 2
INCREMENTAL_MINE_THRESHOLD = 3
MAX_PREFIX_TOKENS = 3
_ASSISTANT_SUGGEST_RE = re.compile(
    r"(?:\?|"
    r"recommend|suggest|should we|want me to|"
    r"\u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434|\u043f\u0440\u0435\u0434\u043b\u0430\u0433|\u0441\u0442\u043e\u0438\u0442 \u043b\u0438"
    r")",
    re.I,
)
_TOKEN_RE = re.compile(r"[\w\u0400-\u04ff]+", re.UNICODE)
_LEARN_CATEGORIES = ("commitment_prefixes", "user_action_verbs")
_USER_TIERS = frozenset({"user_commitment", "user_pattern", "extract_fallback"})
_ASSISTANT_TIERS = frozenset(
    {"assistant_pattern", "assistant_pattern_weak", "assistant_action"}
)


def lang_learned_path(memory_home: Path) -> Path:
    return memory_home / LANG_LEARNED_FILE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_doc() -> dict[str, Any]:
    return {
        "version": LEARNED_VERSION,
        "corpus_chat_ids": [],
        "min_count": MIN_COUNT_DEFAULT,
        "min_distinct_chats": MIN_DISTINCT_CHATS_DEFAULT,
        "categories": {key: [] for key in _LEARN_CATEGORIES},
        "mined_at": None,
    }


def load_lang_learned(memory_home: Path) -> dict[str, Any]:
    path = lang_learned_path(memory_home)
    if not path.is_file():
        return _empty_doc()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_doc()
    if not isinstance(raw, dict):
        return _empty_doc()
    doc = _empty_doc()
    doc["version"] = int(raw.get("version") or LEARNED_VERSION)
    ids = raw.get("corpus_chat_ids")
    if isinstance(ids, list):
        doc["corpus_chat_ids"] = [str(x) for x in ids if x]
    doc["min_count"] = int(raw.get("min_count") or MIN_COUNT_DEFAULT)
    doc["min_distinct_chats"] = int(
        raw.get("min_distinct_chats") or MIN_DISTINCT_CHATS_DEFAULT
    )
    doc["mined_at"] = raw.get("mined_at")
    cats = raw.get("categories")
    if isinstance(cats, dict):
        for key in _LEARN_CATEGORIES:
            rows = cats.get(key)
            if isinstance(rows, list):
                doc["categories"][key] = [
                    r for r in rows if isinstance(r, dict) and r.get("phrase")
                ]
    return doc


def write_lang_learned(memory_home: Path, doc: dict[str, Any]) -> None:
    memory_home.mkdir(parents=True, exist_ok=True)
    lang_learned_path(memory_home).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def project_lang_cues(
    doc: dict[str, Any],
    *,
    min_count: int | None = None,
    min_distinct: int | None = None,
) -> dict[str, list[str]]:
    """Rich doc → flat cue lists (thresholds applied at projection time)."""
    mc = min_count if min_count is not None else int(doc.get("min_count") or MIN_COUNT_DEFAULT)
    md = (
        min_distinct
        if min_distinct is not None
        else int(doc.get("min_distinct_chats") or MIN_DISTINCT_CHATS_DEFAULT)
    )
    out: dict[str, list[str]] = {key: [] for key in _LEARN_CATEGORIES}
    cats = doc.get("categories") or {}
    for key in _LEARN_CATEGORIES:
        rows = cats.get(key) or []
        ranked: list[tuple[int, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            phrase = str(row.get("phrase") or "").strip()
            if not phrase:
                continue
            count = int(row.get("count") or 0)
            chats = row.get("distinct_chats") or []
            distinct = len(chats) if isinstance(chats, list) else 0
            if count < mc or distinct < md:
                continue
            ranked.append((count * distinct, phrase))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        seen: set[str] = set()
        for _score, phrase in ranked:
            low = phrase.lower()
            if low in seen:
                continue
            seen.add(low)
            out[key].append(phrase)
            if len(out[key]) >= 100:
                break
    return out


def _ordered_turns(parsed: ParsedTranscript) -> list[tuple[str, str]]:
    turns: list[tuple[str, str, int]] = []
    for msg in parsed.user_messages:
        clean, _n = sanitize_message(msg.text)
        if clean and not is_terminal_noise(clean):
            turns.append(("user", clean, msg.index))
    for msg in parsed.assistant_blocks:
        text = msg.text.strip()
        if text:
            turns.append(("assistant", text, msg.index))
    turns.sort(key=lambda row: row[2])
    return [(role, text) for role, text, _idx in turns]


def _start_token_phrases(text: str, *, max_tokens: int = MAX_PREFIX_TOKENS) -> list[str]:
    norm = normalize_user_text(text).strip().lower()
    tokens = _TOKEN_RE.findall(norm)
    if not tokens:
        return []
    phrases: list[str] = []
    for n in range(1, min(max_tokens, len(tokens)) + 1):
        phrase = " ".join(tokens[:n])
        if len(phrase) > 64:
            break
        phrases.append(phrase)
    return phrases


def _is_noise_phrase(phrase: str, *, template_phrases: set[str]) -> bool:
    low = phrase.lower().strip()
    if not low or len(low) > 64:
        return True
    if low in GENERIC_MESSAGE_START:
        return True
    if low in template_phrases:
        return True
    tokens = set(_TOKEN_RE.findall(low))
    if tokens and tokens <= GENERIC_MESSAGE_START:
        return True
    return False


def _assistant_suggests(text: str) -> bool:
    tail = text[-800:] if len(text) > 800 else text
    return bool(_ASSISTANT_SUGGEST_RE.search(tail))


def _looks_like_directive(text: str) -> bool:
    norm = normalize_user_text(text).strip()
    if not norm or "?" in norm:
        return False
    if len(norm) < 12:
        return False
    tokens = _TOKEN_RE.findall(norm.lower())
    if not tokens:
        return False
    lead = tokens[0]
    if len(lead) < 3 or lead in DOMAIN_STOPWORDS or lead in GENERIC_MESSAGE_START:
        return False
    return is_pointer_actionable(norm, min_len=12)


def _phrase_index(categories: dict[str, list[dict]], key: str) -> dict[str, dict]:
    return {str(r["phrase"]).lower(): r for r in categories.get(key) or [] if r.get("phrase")}


def _record_phrase(
    index: dict[str, dict],
    *,
    phrase: str,
    chat_id: str,
    example: str,
) -> None:
    low = phrase.lower()
    row = index.get(low)
    if row is None:
        row = {
            "phrase": phrase,
            "count": 0,
            "distinct_chats": [],
            "example_context": example[:200],
        }
        index[low] = row
    row["count"] = int(row.get("count") or 0) + 1
    chats = list(row.get("distinct_chats") or [])
    if chat_id not in chats:
        chats.append(chat_id)
    row["distinct_chats"] = chats


def _mine_chat(
    parsed: ParsedTranscript,
    chat_id: str,
    *,
    template_phrases: set[str],
    commitment_index: dict[str, dict],
    action_index: dict[str, dict],
) -> None:
    turns = _ordered_turns(parsed)
    prev_assistant: str | None = None
    for role, text in turns:
        if role == "assistant":
            prev_assistant = text
            continue
        if role != "user":
            continue
        if _looks_like_directive(text):
            for phrase in _start_token_phrases(text, max_tokens=1):
                if _is_noise_phrase(phrase, template_phrases=template_phrases):
                    continue
                if not is_pointer_actionable(text, min_len=12):
                    continue
                _record_phrase(
                    action_index,
                    phrase=phrase,
                    chat_id=chat_id,
                    example=text[:200],
                )
                break
        if prev_assistant and _assistant_suggests(prev_assistant):
            for phrase in _start_token_phrases(text):
                if _is_noise_phrase(phrase, template_phrases=template_phrases):
                    continue
                tail = text
                low = phrase.lower()
                if text.lower().startswith(low):
                    tail = text[len(phrase) :].lstrip(" ,:;-")
                if not is_pointer_actionable(tail, min_len=12):
                    continue
                if is_generic_only(tail):
                    continue
                _record_phrase(
                    commitment_index,
                    phrase=phrase,
                    chat_id=chat_id,
                    example=text[:200],
                )
        prev_assistant = None


def mine_into_doc(
    doc: dict[str, Any],
    pending: list[dict[str, Any]],
    *,
    memory_home: Path | None = None,
) -> dict[str, Any]:
    """Accumulate cues from pending chats not yet in corpus_chat_ids."""
    corpus = set(doc.get("corpus_chat_ids") or [])
    template = load_lang_cues(memory_home=memory_home)
    template_phrases: set[str] = set()
    for key in _LEARN_CATEGORIES:
        for p in template.get(key) or []:
            template_phrases.add(p.lower())
    for p in template.get("commitment_prefixes") or []:
        template_phrases.add(p.lower())

    categories = doc.get("categories") or {}
    commitment_index = _phrase_index(categories, "commitment_prefixes")
    action_index = _phrase_index(categories, "user_action_verbs")

    mined = 0
    for row in pending:
        chat_id = str(row.get("id") or "")
        jsonl = row.get("jsonl")
        if not chat_id or jsonl is None:
            continue
        if chat_id in corpus:
            continue
        path = Path(jsonl).expanduser()
        if not path.is_file():
            continue
        try:
            parsed = parse_transcript(path)
        except TranscriptSchemaError:
            # A chat can be entirely harness noise (compaction recaps, slash
            # commands). Skip it rather than abort the whole batch.
            corpus.add(chat_id)
            continue
        _mine_chat(
            parsed,
            chat_id,
            template_phrases=template_phrases,
            commitment_index=commitment_index,
            action_index=action_index,
        )
        corpus.add(chat_id)
        mined += 1

    doc["corpus_chat_ids"] = sorted(corpus)
    doc["categories"]["commitment_prefixes"] = sorted(
        commitment_index.values(),
        key=lambda r: (-len(r.get("distinct_chats") or []), -int(r.get("count") or 0)),
    )
    doc["categories"]["user_action_verbs"] = sorted(
        action_index.values(),
        key=lambda r: (-len(r.get("distinct_chats") or []), -int(r.get("count") or 0)),
    )
    doc["mined_at"] = _utc_now()
    doc["chats_mined_this_run"] = mined
    return doc


def new_pending_chat_ids(
    doc: dict[str, Any],
    pending: list[dict[str, Any]],
) -> list[str]:
    corpus = set(doc.get("corpus_chat_ids") or [])
    return [str(r["id"]) for r in pending if str(r.get("id") or "") not in corpus]


def should_incremental_mine(
    doc: dict[str, Any],
    pending: list[dict[str, Any]],
    *,
    threshold: int = INCREMENTAL_MINE_THRESHOLD,
) -> bool:
    return len(new_pending_chat_ids(doc, pending)) >= threshold


def clear_lang_learn_caches() -> None:
    clear_lang_cue_cache()
    clear_pointer_pattern_cache()
    clear_new_task_cache()


def _minimal_extract(jsonl: Path, *, memory_home: Path) -> dict[str, Any]:
    return {
        "user_messages": [],
        "source_path": str(jsonl),
        "memory_home": str(memory_home),
    }


def _tier_bucket(source: str) -> str:
    if source in _USER_TIERS:
        return "user"
    if source in _ASSISTANT_TIERS:
        return "assistant"
    return "other"


def dry_rescore_tier_shift(
    memory_home: Path,
    pending: list[dict[str, Any]],
    *,
    before_doc: dict[str, Any] | None,
    after_doc: dict[str, Any],
) -> dict[str, Any]:
    """Compare pointer tiers with template-only vs learned projection."""
    shifts: list[dict[str, Any]] = []
    before_user = 0
    after_user = 0
    before_assistant = 0
    after_assistant = 0
    conf_delta_sum = 0.0
    conf_delta_n = 0

    before_flat = project_lang_cues(before_doc) if before_doc else {k: [] for k in _LEARN_CATEGORIES}
    after_flat = project_lang_cues(after_doc)

    for row in pending:
        jsonl = row.get("jsonl")
        if jsonl is None:
            continue
        path = Path(jsonl).expanduser()
        if not path.is_file():
            continue
        extract = _minimal_extract(path, memory_home=memory_home)

        b_result = score_extract_with_learned_projection(
            extract,
            memory_home=memory_home,
            learned_flat=before_flat,
        )
        a_result = score_extract_with_learned_projection(
            extract,
            memory_home=memory_home,
            learned_flat=after_flat,
        )

        b_bucket = _tier_bucket(b_result.source)
        a_bucket = _tier_bucket(a_result.source)
        if b_bucket == "user":
            before_user += 1
        elif b_bucket == "assistant":
            before_assistant += 1
        if a_bucket == "user":
            after_user += 1
        elif a_bucket == "assistant":
            after_assistant += 1

        if (
            b_bucket == "assistant"
            and a_bucket == "user"
            and a_result.text
        ):
            shifts.append(
                {
                    "chat_id": row.get("id"),
                    "from": b_result.source,
                    "to": a_result.source,
                    "confidence_delta": round(
                        a_result.confidence - b_result.confidence, 3
                    ),
                }
            )
        if b_result.text and a_result.text and b_result.source != a_result.source:
            conf_delta_sum += a_result.confidence - b_result.confidence
            conf_delta_n += 1

    return {
        "pending": len(pending),
        "before_user": before_user,
        "before_assistant": before_assistant,
        "after_user": after_user,
        "after_assistant": after_assistant,
        "assistant_to_user": len(shifts),
        "avg_confidence_delta": round(conf_delta_sum / conf_delta_n, 3)
        if conf_delta_n
        else 0.0,
        "shifts": shifts[:20],
    }


def corpus_rows_for_mining(
    memory_home: Path,
    pending: list[dict[str, Any]],
    *,
    projects_root: Path,
    days: int = 180,
) -> list[dict[str, Any]]:
    """Pending batch, or full transcript scan when lang_learned is new."""
    if lang_learned_path(memory_home).is_file():
        return pending
    from lib.pending_chats import filter_by_days, scan_transcript_rows

    rows = filter_by_days(scan_transcript_rows(projects_root), days)
    return rows if rows else pending


def prepare_lang_learn_for_batch(
    memory_home: Path,
    pending: list[dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Pre-scan pending jsonl (warms parse cache), mine cues, write lang_learned.json,
    clear lang/pointer caches (not parse cache).
    """
    if not pending:
        return {"status": "skipped", "reason": "empty_pending"}

    doc = load_lang_learned(memory_home)
    new_ids = new_pending_chat_ids(doc, pending)
    if not new_ids and not force:
        return {
            "status": "skipped",
            "reason": "no_new_chats",
            "corpus_size": len(doc.get("corpus_chat_ids") or []),
        }
    if (
        not force
        and doc.get("corpus_chat_ids")
        and len(new_ids) < INCREMENTAL_MINE_THRESHOLD
    ):
        return {
            "status": "skipped",
            "reason": "below_incremental_threshold",
            "new_chats": len(new_ids),
            "threshold": INCREMENTAL_MINE_THRESHOLD,
        }

    before_doc = json.loads(json.dumps(doc))
    from lib.transcript_cursor import TranscriptSchemaError

    usable: list[dict[str, Any]] = []
    skipped_unparseable = 0
    for row in pending:
        jsonl = row.get("jsonl")
        if jsonl is None:
            continue
        path = Path(jsonl).expanduser()
        if not path.is_file():
            continue
        try:
            parse_transcript(path)
        except TranscriptSchemaError:
            # Noise-only / empty transcripts must not abort the batch.
            skipped_unparseable += 1
            continue
        usable.append(row)

    if not usable:
        return {
            "status": "skipped",
            "reason": "no_parseable_pending",
            "skipped_unparseable": skipped_unparseable,
        }

    doc = mine_into_doc(doc, usable, memory_home=memory_home)
    write_lang_learned(memory_home, doc)
    clear_lang_learn_caches()

    summary = dry_rescore_tier_shift(
        memory_home,
        usable,
        before_doc=before_doc,
        after_doc=doc,
    )
    projected = project_lang_cues(doc)
    metric = {
        "event": "lang_learn_summary",
        "status": "ok",
        "chats_mined": doc.get("chats_mined_this_run", 0),
        "corpus_size": len(doc.get("corpus_chat_ids") or []),
        "commitment_cues": len(projected.get("commitment_prefixes") or []),
        "user_action_cues": len(projected.get("user_action_verbs") or []),
        "skipped_unparseable": skipped_unparseable,
        **summary,
    }
    append_metric(memory_home, metric)
    return metric
