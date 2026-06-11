#!/usr/bin/env python3
"""Migrate memory hub from backup — manifest merge + template-aware restore."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.memory_config import (  # noqa: E402
    persist_paths,
    resolve_memory_home,
    resolve_plugin_root,
)
from lib.migrate_hub import format_report_text, migrate_hub  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="from_hub", required=True, help="Source hub path")
    parser.add_argument("--to", dest="to_hub", help="Destination hub (default: MEMORY_HOME)")
    parser.add_argument(
        "--mode",
        choices=("merge", "overwrite", "ignore-existing"),
        default="merge",
        help="merge=manifest merge + replace template stubs (default)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_const",
        const="overwrite",
        dest="mode",
        help="Source wins for all files",
    )
    parser.add_argument(
        "--ignore-existing",
        action="store_const",
        const="ignore-existing",
        dest="mode",
        help="Legacy rsync behavior (deprecated)",
    )
    parser.add_argument(
        "--no-state",
        action="store_true",
        help="Skip .state/, logs/, sources/",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.mode == "ignore-existing":
        print(
            "Warning: --ignore-existing is deprecated; use --merge (default)",
            file=sys.stderr,
        )

    from_path = Path(args.from_hub).expanduser().resolve()
    to_path = resolve_memory_home(args.to_hub, script_file=__file__).resolve()
    plugin_root = resolve_plugin_root(script_file=__file__, memory_home=to_path)
    if plugin_root is None:
        print("Error: could not resolve plugin root", file=sys.stderr)
        return 1

    template_root = plugin_root / "templates"
    report = migrate_hub(
        from_path,
        to_path,
        template_root=template_root,
        mode=args.mode,  # type: ignore[arg-type]
        include_state=not args.no_state,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_text(report))

    if not args.dry_run and report.ok:
        persist_paths(plugin_root.resolve(), to_path)
        if not args.json:
            print(f"  Hub: {to_path} (config updated)")
            print(
                f"  Check: python3 {plugin_root}/scripts/memory-status.py "
                f"--memory-home {to_path}"
            )

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
