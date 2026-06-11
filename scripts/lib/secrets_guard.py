"""Detect and redact secrets — shared by distill-extract and verify-memory.

Regex patterns are a best-effort safety net, not a guarantee.
Use scan_memory_hub(strict=True) for optional high-entropy detection.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from lib.defaults import ENTROPY_MIN_BITS, ENTROPY_MIN_LENGTH

# (label, regex) — order matters: more specific first
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN (?:RSA |DSA |OPENSSH |EC |PGP )?PRIVATE KEY(?: BLOCK)?-----",
            re.I,
        ),
    ),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    # Distinctive multi-char prefixes: no \b anchors so URL-encoded / concatenated
    # secrets (e.g. ...%22GOCSPX-...%22) are still caught; the char class bounds the match.
    (
        "github_token",
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    ),
    (
        "github_finegrained_pat",
        re.compile(r"github_pat_[A-Za-z0-9_]{50,}"),
    ),
    (
        "gitlab_pat",
        re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    (
        "openai_key",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    ),
    (
        "google_oauth_client_secret",
        re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),
    ),
    (
        "google_recaptcha_key",
        re.compile(r"\b6L[A-Za-z0-9_-]{38}\b"),
    ),
    (
        "google_api_key",
        re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    ),
    (
        "grafana_service_account_token",
        re.compile(r"glsa_[A-Za-z0-9_-]{30,}"),
    ),
    (
        "grafana_cloud_token",
        re.compile(r"glc_[A-Za-z0-9+/=_-]{20,}"),
    ),
    (
        "grafana_legacy_api_key",
        re.compile(r"eyJrIjoi[A-Za-z0-9+/=]{20,}"),
    ),
    (
        "slack_token",
        re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ),
    (
        "slack_webhook",
        re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}"),
    ),
    (
        "stripe_secret_key",
        re.compile(r"(?:sk|rk)_live_[A-Za-z0-9]{20,}"),
    ),
    (
        "twilio_api_key",
        re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    ),
    (
        "sendgrid_key",
        re.compile(r"SG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    ),
    (
        "npm_token",
        re.compile(r"npm_[A-Za-z0-9]{36}"),
    ),
    (
        "pypi_token",
        re.compile(r"pypi-AgEI[A-Za-z0-9_-]{20,}"),
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I),
    ),
    (
        "htpasswd_hash",
        re.compile(r"\$(?:apr1|2[aby]|5\$)[^\s:$]{8,}"),
    ),
    (
        "password_assignment",
        re.compile(
            r"(?i)(?:password|passwd|pwd|secret|token|api[_-]?key|db_pass(?:word)?)"
            r"\s*=\s*['\"]?[^\s'\"#,;]{4,}",
        ),
    ),
    (
        "password_colon",
        re.compile(
            r"(?i)(?:password|passwd|pwd|secret|token|api[_-]?key|db_pass(?:word)?)"
            r"\s*:\s*['\"]?[A-Za-z0-9@#$%^&*+/=_]{6,}\b",
        ),
    ),
    (
        "mysql_password_cli",
        re.compile(r"mysql\b[^\n]*\s-p\s*['\"]?[^\s'\"]{3,}", re.I),
    ),
    (
        "basic_auth_url",
        re.compile(r"https?://[^\s:@/]+:[^\s@/]+@", re.I),
    ),
]

REDACTED_PLACEHOLDER = "[REDACTED-SECRET]"

_TERMINAL_MARKERS = (
    "Last login:",
    "xcode-select:",
    "zsh: command not found",
    "permission denied:",
)


def is_terminal_noise(text: str) -> bool:
    if any(m in text for m in _TERMINAL_MARKERS):
        return True
    if re.search(r"@[\w.-]+\s+%\s", text):
        return True
    return False

# Short messages that only reference secret file paths (drop from distill)
DROP_LINE_PATTERNS = [
    re.compile(r"\.env\b", re.I),
    re.compile(r"db_config\.local", re.I),
    re.compile(r"\.admpassfile", re.I),
]


def find_secret_labels(text: str) -> list[str]:
    found: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            found.append(label)
    return found


def contains_secret(text: str, *, strict: bool = False) -> bool:
    if find_secret_labels(text):
        return True
    if strict and find_entropy_secrets(text):
        return True
    return False


def shannon_entropy(data: str) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


_ENTROPY_ALPHABET = re.compile(r"^[A-Za-z0-9+/=_-]+$")


def find_entropy_secrets(text: str) -> list[str]:
    """High-entropy tokens without known prefix — strict mode only."""
    hits: list[str] = []
    for token in re.findall(r"[A-Za-z0-9+/=_-]{20,}", text):
        if len(token) < ENTROPY_MIN_LENGTH:
            continue
        if not _ENTROPY_ALPHABET.match(token):
            continue
        if shannon_entropy(token) >= ENTROPY_MIN_BITS:
            hits.append(token)
    return hits


def should_drop_message(text: str) -> bool:
    """Drop messages that are purely about secret file paths."""
    lower = text.lower()
    return any(p.search(lower) for p in DROP_LINE_PATTERNS) and len(text) < 200


def redact_secrets(text: str) -> tuple[str, int]:
    """Return (redacted_text, number_of_substitutions)."""
    out = text
    total = 0
    for _label, pattern in SECRET_PATTERNS:
        out, n = pattern.subn(REDACTED_PLACEHOLDER, out)
        total += n
    return out, total


def sanitize_message(text: str) -> tuple[str | None, int]:
    """
    Sanitize one user message for distill.
    Returns (None, 0) if message should be dropped entirely.
    """
    if should_drop_message(text):
        return None, 0
    redacted, n = redact_secrets(text)
    if REDACTED_PLACEHOLDER in redacted and len(redacted.replace(REDACTED_PLACEHOLDER, "").strip()) < 20:
        return None, n
    return redacted, n


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """
    Scan file for secrets. Returns list of (line_no, label, line_preview).
    Skips lines that are only [REDACTED-SECRET] placeholders.
    """
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if REDACTED_PLACEHOLDER in line:
            continue
        if is_terminal_noise(line):
            continue
        labels = find_secret_labels(line)
        if labels:
            preview = line.strip()[:80]
            hits.append((i, labels[0], preview))
            continue
    return hits


def scan_file_strict(path: Path) -> list[tuple[int, str, str]]:
    """Regex + high-entropy scan."""
    hits = scan_file(path)
    if not path.is_file():
        return hits
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for i, line in enumerate(text.splitlines(), start=1):
        if REDACTED_PLACEHOLDER in line or is_terminal_noise(line):
            continue
        if find_secret_labels(line):
            continue
        for token in find_entropy_secrets(line):
            preview = line.strip()[:80]
            hits.append((i, "high_entropy", preview))
            break
    return hits


def scan_memory_hub(
    memory_home: Path,
    *,
    strict: bool = False,
) -> list[tuple[Path, int, str, str]]:
    """Scan hub .md/.json for leaked secrets. Returns (path, line, label, preview)."""
    all_hits: list[tuple[Path, int, str, str]] = []
    globs = [
        "context/**/*.md",
        "feedback/**/*.md",
        "chats/**/*.md",
        "chats/**/*.json",
    ]
    for pattern in globs:
        for path in memory_home.glob(pattern):
            if "archive" in path.parts:
                continue
            scanner = scan_file_strict if strict else scan_file
            for line_no, label, preview in scanner(path):
                all_hits.append((path, line_no, label, preview))
    return all_hits
