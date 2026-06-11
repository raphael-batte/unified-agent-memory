"""Central thresholds for agent-memory scripts."""

from __future__ import annotations

from typing import Any

# Distill
MAX_DISTILL_MESSAGES = 30
AUTO_SPREAD_THRESHOLD = 50
APPLY_REVIEW_MAX_DAYS = 7
MIN_NEW_USER_MESSAGES = 2
DISTILL_TOKEN_BUDGET = 12000
MAP_REDUCE_THRESHOLD = 80
MAP_REDUCE_WINDOW_SIZE = 25
ASSISTANT_SNIPPET_MAX = 5
BOUNDARY_DEBOUNCE_SECONDS = 30
POINTER_LOW_CONFIDENCE = 0.6
SEGMENT_PAUSE_MINUTES = 30
SEGMENT_JACCARD_WINDOW = 5
SEGMENT_JACCARD_MIN = 0.15
ROLLING_COMPACTION_ENQUEUE = 15
ROLLING_COMPACTION_HARD_CAP = 25
ROLLING_SUMMARY_MAX = 12
HUB_RETENTION_DAYS = 30

# Layer rotation / verify
MAX_LAYER_FILE_LINES = 100
ROTATION_WARN_LINES = 80

# Secrets (strict / entropy mode)
ENTROPY_MIN_LENGTH = 24
ENTROPY_MIN_BITS = 4.5

DEFAULT_KEYWORDS = (
    "deploy",
    "decision",
    "prod",
    "migration",
    "docker",
    "ssl",
    "canonical",
    "architecture",
)

# Cross-layer overlap: domain tokens too common to signal duplication
DOMAIN_STOPWORDS = frozenset(
    {
        "deploy",
        "deployment",
        "docker",
        "branch",
        "merge",
        "test",
        "tests",
        "ci",
        "fix",
        "prod",
        "production",
        "staging",
        "commit",
        "push",
        "pull",
        "repo",
        "github",
        "workflow",
        "build",
        "run",
        "file",
        "files",
        "code",
        "project",
        "memory",
        "agent",
        "cursor",
        "script",
        "scripts",
    }
)

CROSS_LAYER_MAX_DF = 2
CROSS_LAYER_MIN_SHARED_BIGRAMS = 2


def load_thresholds(hub_config: dict[str, Any] | None = None) -> dict[str, int]:
    """Merge hub config.json thresholds over framework defaults."""
    out = {
        "max_distill_messages": MAX_DISTILL_MESSAGES,
        "auto_spread_threshold": AUTO_SPREAD_THRESHOLD,
        "distill_token_budget": DISTILL_TOKEN_BUDGET,
        "map_reduce_threshold": MAP_REDUCE_THRESHOLD,
        "map_reduce_window_size": MAP_REDUCE_WINDOW_SIZE,
        "segment_pause_minutes": SEGMENT_PAUSE_MINUTES,
        "segment_jaccard_window": SEGMENT_JACCARD_WINDOW,
        "rolling_compaction_enqueue": ROLLING_COMPACTION_ENQUEUE,
        "rolling_compaction_hard_cap": ROLLING_COMPACTION_HARD_CAP,
        "rolling_summary_max": ROLLING_SUMMARY_MAX,
        "retention_days": HUB_RETENTION_DAYS,
        "max_layer_file_lines": MAX_LAYER_FILE_LINES,
        "rotation_warn_lines": ROTATION_WARN_LINES,
    }
    floats = {
        "segment_jaccard_min": SEGMENT_JACCARD_MIN,
    }
    if not hub_config:
        return {**out, **floats}
    custom = hub_config.get("thresholds") or {}
    if isinstance(custom, dict):
        for key in out:
            if key in custom and isinstance(custom[key], int):
                out[key] = custom[key]
        for key in floats:
            val = custom.get(key)
            if isinstance(val, (int, float)):
                floats[key] = float(val)
    return {**out, **floats}
