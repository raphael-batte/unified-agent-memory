"""Hub migration — manifest merge, template-aware restore, observable reports."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from lib.chats_manifest import load_manifest, merge_manifests, save_manifest

MigrateMode = Literal["merge", "overwrite", "ignore-existing"]

# Copy missing user data; never blindly overwrite curated content in merge mode.
DATA_SUBDIRS = (
    "chats/projects",
    "chats/merge-staging",
    "chats/extracts",
    "chats/map-staging",
    "chats/reduce-staging",
    "chats/rolling",
    "chats/archive",
)

TEMPLATE_AWARE_PREFIXES = (
    "context/",
    "feedback/",
)

CHATS_TEMPLATE_REL = frozenset(
    {
        "chats/INDEX.md",
        "chats/manifest.json",
        "chats/semantic-merge-prompt.md",
        "chats/pointer-curate-prompt.md",
        "chats/archive/README.md",
        "chats/transcripts/README.md",
        "chats/projects/example.md",
    }
)

OPTIONAL_TOP_DIRS = (".state", "sources", "logs")


@dataclass
class TreeReport:
    copied: int = 0
    skipped_user: int = 0
    template_replaced: int = 0
    overwritten: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "copied": self.copied,
            "skipped_user": self.skipped_user,
            "template_replaced": self.template_replaced,
            "overwritten": self.overwritten,
        }


@dataclass
class MigrateReport:
    mode: MigrateMode
    source: str
    destination: str
    dry_run: bool = False
    manifest: dict[str, Any] = field(default_factory=dict)
    trees: dict[str, TreeReport] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def tree(self, name: str) -> TreeReport:
        if name not in self.trees:
            self.trees[name] = TreeReport()
        return self.trees[name]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "source": self.source,
            "destination": self.destination,
            "dry_run": self.dry_run,
            "manifest": self.manifest,
            "trees": {k: v.as_dict() for k, v in self.trees.items()},
            "warnings": self.warnings,
            "errors": self.errors,
        }


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_identical(a: Path, b: Path) -> bool:
    if not a.is_file() or not b.is_file():
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    return file_digest(a) == file_digest(b)


def template_path(template_root: Path, rel: str) -> Path | None:
    """Map hub-relative path to templates/ path if it exists."""
    rel = rel.replace("\\", "/").lstrip("/")
    candidates = [template_root / rel]
    if rel.startswith("chats/"):
        candidates.append(template_root / rel)
    elif rel == "config.json":
        candidates.append(template_root / "config.json")
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def dest_is_unchanged_template(
    dest_file: Path,
    template_root: Path,
    rel: str,
) -> bool:
    tpl = template_path(template_root, rel)
    if tpl is None:
        return False
    return files_identical(dest_file, tpl)


def _copy_file(src: Path, dest: Path, *, dry_run: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        shutil.copy2(src, dest)


def migrate_manifest_file(
    source_hub: Path,
    dest_hub: Path,
    *,
    mode: MigrateMode,
    dry_run: bool,
    report: MigrateReport,
) -> None:
    src_manifest = source_hub / "chats" / "manifest.json"
    dest_manifest = dest_hub / "chats" / "manifest.json"
    if not src_manifest.is_file():
        report.warnings.append("manifest: source missing — skipped")
        return

    source_data = load_manifest(src_manifest)
    source_n = len(source_data.get("processed") or [])

    if mode == "overwrite" or not dest_manifest.is_file():
        merged = source_data
        stats = {
            "source_processed": source_n,
            "dest_before": 0,
            "added": source_n,
            "updated": 0,
            "merged_total": source_n,
            "action": "copied" if mode == "overwrite" else "created",
        }
    elif mode == "ignore-existing":
        if dest_manifest.is_file():
            dest_n = len(load_manifest(dest_manifest).get("processed") or [])
            stats = {
                "source_processed": source_n,
                "dest_before": dest_n,
                "added": 0,
                "updated": 0,
                "merged_total": dest_n,
                "action": "skipped",
            }
            merged = load_manifest(dest_manifest)
        else:
            merged = source_data
            stats = {
                "source_processed": source_n,
                "dest_before": 0,
                "added": source_n,
                "updated": 0,
                "merged_total": source_n,
                "action": "created",
            }
    else:
        dest_data = load_manifest(dest_manifest)
        dest_n = len(dest_data.get("processed") or [])
        merged, merge_stats = merge_manifests(source_data, dest_data)
        stats = {**merge_stats, "action": "merged"}

    report.manifest = stats
    if stats.get("action") == "skipped":
        if source_n > 0 and stats.get("dest_before", 0) == 0:
            report.errors.append(
                f"manifest: source={source_n} dest=0 but skipped (use --merge or --overwrite)"
            )
        return

    if not dry_run:
        save_manifest(dest_manifest, merged)

    if source_n > 0 and stats.get("merged_total", 0) == 0:
        report.errors.append(
            f"manifest: source={source_n} entries but merged_total=0 — registry not restored"
        )


def _should_copy_file(
    *,
    rel: str,
    src: Path,
    dest: Path,
    template_root: Path,
    mode: MigrateMode,
    tree: TreeReport,
    report: MigrateReport,
) -> bool:
    if not dest.is_file():
        tree.copied += 1
        return True

    if mode == "overwrite":
        tree.overwritten += 1
        return True

    if mode == "ignore-existing":
        tree.skipped_user += 1
        return False

    # merge mode
    if dest_is_unchanged_template(dest, template_root, rel):
        tree.template_replaced += 1
        return True

    if files_identical(src, dest):
        tree.skipped_user += 1
        return False

    tree.skipped_user += 1
    report.warnings.append(f"skipped user-edited file: {rel}")
    return False


def migrate_tree_files(
    source_hub: Path,
    dest_hub: Path,
    subdir: str,
    *,
    template_root: Path,
    mode: MigrateMode,
    dry_run: bool,
    report: MigrateReport,
    template_aware: bool,
) -> None:
    src_root = source_hub / subdir
    if not src_root.is_dir():
        return
    tree = report.tree(subdir.rstrip("/"))

    for src in sorted(src_root.rglob("*")):
        if not src.is_file():
            continue
        rel = str(src.relative_to(source_hub)).replace("\\", "/")
        dest = dest_hub / rel

        if template_aware and not any(rel.startswith(p) for p in TEMPLATE_AWARE_PREFIXES):
            if rel.startswith("chats/") and rel not in CHATS_TEMPLATE_REL:
                # handled by data subdirs
                continue

        if rel.startswith("chats/") and rel not in CHATS_TEMPLATE_REL:
            if not rel.startswith("chats/projects/") and "manifest.json" not in rel:
                # staging handled separately
                if subdir != "chats":
                    pass
                else:
                    continue

        if rel == "chats/manifest.json":
            continue

        if _should_copy_file(
            rel=rel,
            src=src,
            dest=dest,
            template_root=template_root,
            mode=mode,
            tree=tree,
            report=report,
        ):
            _copy_file(src, dest, dry_run=dry_run)


def migrate_data_subdir(
    source_hub: Path,
    dest_hub: Path,
    rel_subdir: str,
    *,
    mode: MigrateMode,
    dry_run: bool,
    report: MigrateReport,
) -> None:
    src_root = source_hub / rel_subdir
    if not src_root.is_dir():
        return
    tree = report.tree(rel_subdir)
    for src in sorted(src_root.rglob("*")):
        if not src.is_file():
            continue
        rel = str(src.relative_to(source_hub)).replace("\\", "/")
        dest = dest_hub / rel
        if not dest.is_file():
            tree.copied += 1
            _copy_file(src, dest, dry_run=dry_run)
        elif mode == "overwrite":
            tree.overwritten += 1
            _copy_file(src, dest, dry_run=dry_run)
        elif not files_identical(src, dest):
            tree.skipped_user += 1
            report.warnings.append(f"skipped existing data file: {rel}")


def migrate_hub_config(
    source_hub: Path,
    dest_hub: Path,
    *,
    template_root: Path,
    mode: MigrateMode,
    dry_run: bool,
    report: MigrateReport,
) -> None:
    src = source_hub / "config.json"
    dest = dest_hub / "config.json"
    if not src.is_file():
        return
    tree = report.tree("config.json")
    rel = "config.json"
    if _should_copy_file(
        rel=rel,
        src=src,
        dest=dest,
        template_root=template_root,
        mode=mode,
        tree=tree,
        report=report,
    ):
        _copy_file(src, dest, dry_run=dry_run)


def migrate_hub(
    source_hub: Path,
    dest_hub: Path,
    *,
    template_root: Path,
    mode: MigrateMode = "merge",
    include_state: bool = True,
    dry_run: bool = False,
) -> MigrateReport:
    source_hub = source_hub.resolve()
    dest_hub = dest_hub.resolve()
    report = MigrateReport(
        mode=mode,
        source=str(source_hub),
        destination=str(dest_hub),
        dry_run=dry_run,
    )

    if not source_hub.is_dir():
        report.errors.append(f"source not found: {source_hub}")
        return report
    if source_hub == dest_hub:
        report.errors.append("source and destination are the same")
        return report

    if not dry_run:
        dest_hub.mkdir(parents=True, exist_ok=True)

    migrate_manifest_file(source_hub, dest_hub, mode=mode, dry_run=dry_run, report=report)

    for prefix in ("context", "feedback"):
        migrate_tree_files(
            source_hub,
            dest_hub,
            prefix,
            template_root=template_root,
            mode=mode,
            dry_run=dry_run,
            report=report,
            template_aware=True,
        )

    # chats template files (INDEX, prompts, example)
    chats_tpl_src = source_hub / "chats"
    if chats_tpl_src.is_dir():
        tree = report.tree("chats/templates")
        for rel in sorted(CHATS_TEMPLATE_REL):
            if rel == "chats/manifest.json":
                continue
            src = source_hub / rel
            if not src.is_file():
                continue
            dest = dest_hub / rel
            if _should_copy_file(
                rel=rel,
                src=src,
                dest=dest,
                template_root=template_root,
                mode=mode,
                tree=tree,
                report=report,
            ):
                _copy_file(src, dest, dry_run=dry_run)

    for sub in DATA_SUBDIRS:
        migrate_data_subdir(
            source_hub,
            dest_hub,
            sub,
            mode=mode,
            dry_run=dry_run,
            report=report,
        )

    migrate_hub_config(
        source_hub,
        dest_hub,
        template_root=template_root,
        mode=mode,
        dry_run=dry_run,
        report=report,
    )

    if include_state:
        for sub in OPTIONAL_TOP_DIRS:
            migrate_data_subdir(
                source_hub,
                dest_hub,
                sub,
                mode=mode,
                dry_run=dry_run,
                report=report,
            )

    src_readme = source_hub / "README.md"
    dest_readme = dest_hub / "README.md"
    if src_readme.is_file():
        tree = report.tree("README.md")
        if _should_copy_file(
            rel="README.md",
            src=src_readme,
            dest=dest_readme,
            template_root=template_root,
            mode=mode,
            tree=tree,
            report=report,
        ):
            _copy_file(src_readme, dest_readme, dry_run=dry_run)

    return report


def format_report_text(report: MigrateReport) -> str:
    lines = [
        "Migrate memory hub",
        f"  From: {report.source}",
        f"  To:   {report.destination}",
        f"  Mode: {report.mode}" + (" (dry-run)" if report.dry_run else ""),
        "",
    ]
    if report.manifest:
        m = report.manifest
        action = m.get("action", "merged")
        lines.append(
            "  manifest: "
            f"source={m.get('source_processed', 0)} "
            f"dest_before={m.get('dest_before', 0)} "
            f"→ {action.upper()} total={m.get('merged_total', 0)} "
            f"(+{m.get('added', 0)} ~{m.get('updated', 0)})"
        )
    for name, tree in sorted(report.trees.items()):
        t = tree.as_dict()
        total = t["copied"] + t["template_replaced"] + t["overwritten"]
        if total == 0 and t["skipped_user"] == 0:
            continue
        lines.append(
            f"  {name}: copied={t['copied']} template_replaced={t['template_replaced']} "
            f"overwritten={t['overwritten']} skipped={t['skipped_user']}"
        )
    if report.warnings:
        lines.append("")
        for w in report.warnings[:10]:
            lines.append(f"  ⚠ {w}")
        if len(report.warnings) > 10:
            lines.append(f"  ⚠ … +{len(report.warnings) - 10} more")
    if report.errors:
        lines.append("")
        for e in report.errors:
            lines.append(f"  ✗ {e}")
    lines.append("")
    if report.ok:
        lines.append("Done.")
    else:
        lines.append("Done with errors.")
    return "\n".join(lines)
