#!/usr/bin/env python3
"""Command-line runner for the bierre literature workflow.

Examples:
    python cli.py --offline
    python cli.py -q "antimicrobial hydrogel wound dressing"
    python cli.py -q "graphene supercapacitor electrodes" --profile generic
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import Settings, available_profiles, load_profile, run_pipeline  # noqa: E402


class _ConsoleProgress:
    """Tiny stderr progress bar with an ETA estimate."""

    def __init__(self) -> None:
        self.start = time.time()

    def __call__(self, step: int, total: int, label: str) -> None:
        total = max(total, 1)
        filled = int(28 * step / total)
        bar = "#" * filled + "-" * (28 - filled)
        elapsed = time.time() - self.start
        eta = int(elapsed / max(step, 1) * max(total - step, 0))
        end = "\n" if step >= total else ""
        print(f"\r[{bar}] {step}/{total} {label[:46]:<46} ETA {eta:>3}s", end=end, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bierre literature search and triage")
    parser.add_argument("-q", "--question", default="", help="Research question to search.")
    parser.add_argument("--offline", action="store_true", help="Use built-in mock records (no network).")
    parser.add_argument("--profile", help="Domain profile name (overrides config).")
    parser.add_argument("--config", type=Path, help="Path to a settings YAML file.")
    parser.add_argument("--json", type=Path, help="Write the full result as JSON to this path.")
    parser.add_argument("--quiet", action="store_true", help="Suppress the progress bar.")
    args = parser.parse_args(argv)

    settings = Settings.load(args.config)
    if args.profile:
        settings.profile = args.profile
    profile = load_profile(settings.profile)

    result = run_pipeline(
        question=args.question,
        settings=settings,
        profile=profile,
        offline=args.offline,
        progress=None if args.quiet else _ConsoleProgress(),
    )

    print(f"\nProfile: {result.profile}  |  Mode: {result.mode}  |  Run: {result.run_id}")
    print(f"Question: {result.question}")
    print(f"Found {len(result.ranked)} papers, selected {len(result.selected)}.")
    print(f"Sources used: {', '.join(result.apis_used) or 'none'}")
    if available_profiles():
        print(f"(Available profiles: {', '.join(available_profiles())})")
    print("\nTop selected papers:")
    for item in result.selected[:10]:
        print(f"  [{item.relevance:5.1f}%] {item.bucket_label:<28} {item.paper.title[:70]}")
    if result.errors:
        print(f"\n{len(result.errors)} warning(s) recorded (non-fatal).")

    if args.json:
        args.json.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
