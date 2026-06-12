"""BM25-lite search over hub markdown bullets and optional extract JSON."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from lib.defaults import DOMAIN_STOPWORDS, HUB_RETENTION_DAYS, load_thresholds
from lib.distill_metrics import append_metric
from lib.markdown_sections import (
    bullets,
    chat_id_from_bullet,
    last_updated_from_preamble,
    paragraph_units,
    parse_sections,
)
from lib.memory_config import load_hub_config
from lib.novelty import normalize_snippet
from lib.search_lang import expand_query_tokens, load_search_synonyms
from lib.timestamps import parse_distilled_at

_TOKEN_RE = re.compile(r"[\w\u0400-\u04ff]+", re.UNICODE)
_PREFIX_LEN = 4
_RECENCY_HALF_LIFE_DAYS = 60.0
_SEARCH_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "to", "in", "on", "for", "is", "it", "we", "you", "of", "at"}
)

_SECTION_WEIGHTS: dict[str, float] = {
    "decisions": 2.0,
    "next step": 1.8,
    "summary": 1.5,
    "recent": 1.2,
    "preferences": 1.3,
    "open threads": 1.1,
}
_LAYER_WEIGHTS: dict[str, float] = {
    "chats": 1.0,
    "context": 1.2,
    "feedback": 1.4,
    "extract": 0.9,
}
_ARCHIVE_WEIGHT = 0.7

BM25_K1 = 1.2
BM25_B = 0.75


@dataclass(frozen=True)
class SearchDoc:
    text: str
    rel_path: str
    section: str
    layer: str
    date: str | None
    chat_id: str | None = None
    archived: bool = False


@dataclass(frozen=True)
class SearchHit:
    text: str
    rel_path: str
    section: str
    layer: str
    date: str | None
    score: float
    chat_id: str | None = None
    drill: str | None = None


def _prefix_key(token: str) -> str:
    t = token.lower()
    if len(t) >= _PREFIX_LEN:
        return t[:_PREFIX_LEN]
    return t


def tokenize(text: str) -> list[str]:
    raw = [_prefix_key(tok) for tok in _TOKEN_RE.findall(text.lower()) if len(tok) > 2]
    return [t for t in raw if t not in DOMAIN_STOPWORDS and t not in _SEARCH_STOPWORDS]


def _section_weight(section: str, *, archived: bool) -> float:
    key = section.strip().lower()
    base = _SECTION_WEIGHTS.get(key, 1.0)
    if archived:
        base *= _ARCHIVE_WEIGHT
    return base


def _parse_doc_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return parse_distilled_at(value[:19] if "T" in value else value[:10])


def _recency_boost(doc_date: str | None, *, now: datetime | None = None) -> float:
    ref = now or datetime.now()
    parsed = _parse_doc_date(doc_date)
    if parsed is None:
        return 1.0
    days = max(0.0, (ref - parsed).total_seconds() / 86400.0)
    return 0.5 + 0.5 * math.exp(-days / _RECENCY_HALF_LIFE_DAYS)


def _iter_markdown_files(memory_home: Path, sub: str) -> list[Path]:
    root = memory_home / sub
    if not root.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        if "merge-staging" in path.parts or "map-staging" in path.parts:
            continue
        out.append(path)
    return out


def _layer_from_path(memory_home: Path, path: Path) -> tuple[str, bool]:
    rel = path.relative_to(memory_home)
    parts = rel.parts
    archived = "archive" in parts
    if parts[0] == "chats":
        return "chats", archived
    if parts[0] == "context":
        return "context", archived
    if parts[0] == "feedback":
        return "feedback", archived
    return "hub", archived


def _docs_from_markdown(
    memory_home: Path,
    path: Path,
    *,
    layer_filter: set[str] | None,
) -> list[SearchDoc]:
    layer, archived = _layer_from_path(memory_home, path)
    if layer_filter and layer not in layer_filter:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if archived:
        from lib.project_merge import _ensure_archive_decisions_section  # noqa: WPS433

        slug = path.stem.removesuffix("-decisions") if path.stem.endswith("-decisions") else path.stem
        text = _ensure_archive_decisions_section(text, slug=slug)
    preamble, sections = parse_sections(text)
    doc_date = last_updated_from_preamble(preamble)
    rel = str(path.relative_to(memory_home))
    docs: list[SearchDoc] = []

    for section_name, body in sections.items():
        if not body.strip():
            continue
        chat_id = None
        for unit in bullets(body):
            if chat_id is None:
                chat_id = chat_id_from_bullet(unit)
            docs.append(
                SearchDoc(
                    text=unit,
                    rel_path=rel,
                    section=section_name,
                    layer=layer,
                    date=doc_date,
                    chat_id=chat_id,
                    archived=archived,
                )
            )
        if layer == "context":
            for para in paragraph_units(body):
                docs.append(
                    SearchDoc(
                        text=para,
                        rel_path=rel,
                        section=section_name,
                        layer=layer,
                        date=doc_date,
                        archived=archived,
                    )
                )
    return docs


def _extract_snippets(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (section_label, text) pairs from extract JSON."""
    out: list[tuple[str, str]] = []
    fq = str(data.get("first_query") or "").strip()
    if fq:
        out.append(("first_query", fq))
    fs = str(data.get("final_summary") or "").strip()
    if fs:
        out.append(("summary", fs))
    for idx, bullet in enumerate(data.get("summary_bullets") or []):
        if isinstance(bullet, str) and bullet.strip():
            out.append((f"summary_{idx}", bullet.strip()[:400]))
    for idx, row in enumerate(data.get("decision_candidates") or []):
        if isinstance(row, dict):
            text = str(row.get("text") or "").strip()
            if text:
                out.append((f"decision_{idx}", text[:400]))
    for seg in data.get("topic_segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = seg.get("segment", "?")
        for j, bullet in enumerate(seg.get("bullets") or []):
            if isinstance(bullet, str) and bullet.strip():
                out.append((f"segment_{sid}_{j}", bullet.strip()[:400]))
    for idx, msg in enumerate(data.get("user_messages") or []):
        if isinstance(msg, str) and msg.strip():
            out.append((f"user_{idx}", msg.strip()[:400]))
    for idx, snip in enumerate(data.get("assistant_snippets") or []):
        if isinstance(snip, str) and snip.strip():
            out.append((f"assistant_{idx}", snip.strip()[:400]))
    for idx, bullet in enumerate(data.get("rolling_summary") or []):
        if isinstance(bullet, str) and bullet.strip():
            out.append((f"rolling_{idx}", bullet.strip()[:400]))
    return out


def _docs_from_extracts(
    memory_home: Path,
    *,
    retention_days: int,
) -> tuple[list[SearchDoc], int, int]:
    extracts_dir = memory_home / "chats" / "extracts"
    if not extracts_dir.is_dir():
        return [], 0, 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    docs: list[SearchDoc] = []
    eligible = 0
    purged = 0
    for path in sorted(extracts_dir.glob("*.json")):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            purged += 1
            continue
        eligible += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        chat_id = str(data.get("uuid") or path.stem)
        date = str(data.get("date") or mtime.strftime("%Y-%m-%d"))
        rel = str(path.relative_to(memory_home))
        for section, text in _extract_snippets(data):
            docs.append(
                SearchDoc(
                    text=text,
                    rel_path=rel,
                    section=section,
                    layer="extract",
                    date=date,
                    chat_id=chat_id,
                )
            )
    return docs, eligible, purged


def build_corpus(
    memory_home: Path,
    *,
    layers: set[str] | None = None,
    include_extracts: bool = False,
    retention_days: int = HUB_RETENTION_DAYS,
) -> tuple[list[SearchDoc], dict[str, Any]]:
    """Collect searchable documents from hub layers."""
    layer_filter = layers
    docs: list[SearchDoc] = []
    for sub in ("chats", "context", "feedback"):
        for path in _iter_markdown_files(memory_home, sub):
            docs.extend(_docs_from_markdown(memory_home, path, layer_filter=layer_filter))

    meta: dict[str, Any] = {"hub_docs": len(docs)}
    if include_extracts:
        extract_docs, eligible, purged = _docs_from_extracts(
            memory_home, retention_days=retention_days
        )
        if layer_filter is None or "extract" in layer_filter:
            docs.extend(extract_docs)
        meta["extracts_eligible"] = eligible
        meta["extracts_purged_by_retention"] = purged
        meta["extract_docs"] = len(extract_docs)
    docs = _dedupe_search_docs(docs)
    meta["hub_docs"] = len(docs)
    return docs, meta


def _dedupe_search_docs(docs: list[SearchDoc]) -> list[SearchDoc]:
    """One searchable doc per (path, normalized text) — drops duplicate archive bullets."""
    seen: set[tuple[str, str]] = set()
    out: list[SearchDoc] = []
    for doc in docs:
        key = (doc.rel_path, normalize_snippet(doc.text))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out


def _term_freqs(tokens: list[str]) -> dict[str, int]:
    freq: dict[str, int] = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1
    return freq


def _doc_length(freqs: dict[str, int]) -> int:
    return sum(freqs.values()) or 1


def _tokens_match(query_tok: str, doc_tok: str) -> bool:
    if query_tok == doc_tok:
        return True
    n = min(len(query_tok), len(doc_tok), _PREFIX_LEN)
    return n >= 3 and query_tok[:n] == doc_tok[:n]


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    *,
    avg_dl: float,
    doc_freq: dict[str, int],
    n_docs: int,
) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    freqs = _term_freqs(doc_tokens)
    dl = _doc_length(freqs)
    score = 0.0
    for q in query_tokens:
        tf = 0
        for dt, count in freqs.items():
            if _tokens_match(q, dt):
                tf += count
        if tf == 0:
            continue
        df = doc_freq.get(q, 0)
        for dt in freqs:
            if _tokens_match(q, dt):
                df = max(df, doc_freq.get(dt, 0))
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / avg_dl)
        score += idf * (tf * (BM25_K1 + 1.0)) / denom
    return score


def _build_doc_freq(docs: list[SearchDoc]) -> tuple[list[list[str]], dict[str, int], float]:
    tokenized: list[list[str]] = []
    doc_freq: dict[str, int] = {}
    total_len = 0
    for doc in docs:
        toks = tokenize(doc.text)
        tokenized.append(toks)
        total_len += len(toks) or 1
        seen: set[str] = set()
        for t in toks:
            if t not in seen:
                doc_freq[t] = doc_freq.get(t, 0) + 1
                seen.add(t)
    avg_dl = total_len / max(len(docs), 1)
    return tokenized, doc_freq, avg_dl


def search_hub(
    memory_home: Path,
    query: str,
    *,
    top: int = 8,
    layers: set[str] | None = None,
    deep: bool = False,
    retention_days: int | None = None,
    log_metrics: bool = True,
) -> dict[str, Any]:
    hub_cfg = load_hub_config(memory_home)
    thresholds = load_thresholds(hub_cfg)
    retain = int(retention_days if retention_days is not None else thresholds["retention_days"])

    include_layers = set(layers) if layers else {"chats", "context", "feedback"}
    if deep:
        include_layers.add("extract")

    docs, meta = build_corpus(
        memory_home,
        layers=include_layers,
        include_extracts=deep,
        retention_days=retain,
    )
    if not docs:
        result = {
            "status": "ok",
            "query": query,
            "hits": [],
            "meta": meta,
            "retention_days": retain,
            "warning": None,
        }
        if log_metrics:
            append_metric(
                memory_home,
                {
                    "event": "search_query",
                    "query_preview": query[:80],
                    "hits": 0,
                    "deep": deep,
                },
            )
        return result

    synonyms = load_search_synonyms(memory_home=memory_home)
    query_tokens = expand_query_tokens(tokenize(query), synonyms)
    tokenized, doc_freq, avg_dl = _build_doc_freq(docs)
    n_docs = len(docs)

    hits: list[SearchHit] = []
    for doc, doc_tokens in zip(docs, tokenized):
        bm25 = _bm25_score(
            query_tokens,
            doc_tokens,
            avg_dl=avg_dl,
            doc_freq=doc_freq,
            n_docs=n_docs,
        )
        if bm25 <= 0:
            continue
        sw = _section_weight(doc.section, archived=doc.archived)
        lw = _LAYER_WEIGHTS.get(doc.layer, 1.0)
        rb = _recency_boost(doc.date)
        score = bm25 * sw * lw * rb
        drill = None
        if doc.chat_id and doc.layer in ("chats", "extract"):
            title = doc.text[:60].replace("\n", " ").strip() or "chat"
            drill = f"[{title}]({doc.chat_id})"
        hits.append(
            SearchHit(
                text=doc.text,
                rel_path=doc.rel_path,
                section=doc.section,
                layer=doc.layer,
                date=doc.date,
                score=score,
                chat_id=doc.chat_id,
                drill=drill,
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    top_hits = hits[: max(top, 1)]

    warning = None
    if deep and meta.get("extracts_purged_by_retention", 0) > 0:
        warning = (
            f"Deep search uses extracts within {retain}d retention; "
            f"{meta['extracts_purged_by_retention']} older extract(s) excluded "
            "(same as memory-doctor --fix cleanup)."
        )

    if log_metrics:
        append_metric(
            memory_home,
            {
                "event": "search_query",
                "query_preview": query[:80],
                "hits": len(top_hits),
                "deep": deep,
                "corpus_size": len(docs),
            },
        )

    return {
        "status": "ok",
        "query": query,
        "hits": [
            {
                "text": h.text,
                "path": h.rel_path,
                "section": h.section,
                "layer": h.layer,
                "date": h.date,
                "score": round(h.score, 4),
                "chat_id": h.chat_id,
                "drill": h.drill,
            }
            for h in top_hits
        ],
        "meta": meta,
        "retention_days": retain,
        "warning": warning,
    }
