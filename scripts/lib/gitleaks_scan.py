"""Optional gitleaks integration — separate from default regex scan."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def gitleaks_available() -> bool:
    return shutil.which("gitleaks") is not None


def _gitleaks_supports_dir() -> bool:
    if not gitleaks_available():
        return False
    try:
        proc = subprocess.run(
            ["gitleaks", "dir", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def resolve_gitleaks_config(target: Path) -> Path | None:
    """Return .gitleaks.toml next to target (dir or file parent)."""
    root = target if target.is_dir() else target.parent
    cfg = (root / ".gitleaks.toml").resolve()
    return cfg if cfg.is_file() else None


def _build_gitleaks_cmd(
    target: Path,
    report_path: Path,
    *,
    config: Path | None = None,
) -> list[str]:
    resolved = str(target.resolve())
    config_args: list[str] = []
    if config is not None and config.is_file():
        config_args = ["--config", str(config.resolve())]

    if _gitleaks_supports_dir():
        return [
            "gitleaks",
            "dir",
            resolved,
            *config_args,
            "--report-path",
            str(report_path),
            "--report-format",
            "json",
            "--exit-code",
            "0",
        ]
    return [
        "gitleaks",
        "detect",
        "--source",
        resolved,
        *config_args,
        "--report-path",
        str(report_path),
        "--report-format",
        "json",
        "--no-git",
        "--exit-code",
        "0",
    ]


def scan_path_with_gitleaks(
    target: Path,
    *,
    timeout_sec: int = 120,
) -> tuple[list[dict], str | None]:
    """
    Run gitleaks on a directory or file.
    Uses `gitleaks dir` when available (8.19+), else `detect --no-git`.
    Returns (findings list, error message if tool failed).
    """
    if not gitleaks_available():
        return [], "gitleaks not installed (brew install gitleaks)"

    if not target.exists():
        return [], f"path not found: {target}"

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)

    config = resolve_gitleaks_config(target)
    cmd = _build_gitleaks_cmd(target, report_path, config=config)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report_path.unlink(missing_ok=True)
        return [], str(exc)

    if not report_path.is_file():
        report_path.unlink(missing_ok=True)
        return [], proc.stderr.strip() or "gitleaks produced no report"

    try:
        raw = report_path.read_text(encoding="utf-8")
        findings = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        findings = []
    finally:
        report_path.unlink(missing_ok=True)

    if not isinstance(findings, list):
        findings = []

    if proc.returncode not in (0, 1):
        return findings, proc.stderr.strip() or f"gitleaks exit {proc.returncode}"

    return findings, None


def findings_to_hits(
    findings: list[dict],
    memory_home: Path,
) -> list[tuple[Path, int, str, str]]:
    hits: list[tuple[Path, int, str, str]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        fpath = item.get("File") or item.get("file") or ""
        if not fpath:
            continue
        path = Path(fpath)
        try:
            path.relative_to(memory_home)
        except ValueError:
            continue
        line = int(item.get("StartLine") or item.get("line") or 0)
        rule = str(item.get("RuleID") or item.get("rule") or "gitleaks")
        preview = str(item.get("Match") or item.get("Secret") or "")[:80]
        hits.append((path, line, f"gitleaks:{rule}", preview))
    return hits
