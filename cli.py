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

from core import ProfileService, RunSearchRequest, SearchService, Settings, build_profile_repository  # noqa: E402
from core.repositories.profile_repository import DomainProfile  # noqa: E402


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
    profile_service = ProfileService(repository=build_profile_repository(settings))

    def _profile_loader(profile_id: str) -> DomainProfile:
        return DomainProfile.from_dict(profile_service.get_profile(profile_id))

    service = SearchService(base_settings=settings, profile_loader=_profile_loader)
    # Keep legacy CLI behavior: empty --question falls back to profile default.
    profile = _profile_loader(settings.profile)
    question = str(args.question or "").strip() or profile.default_question

    response = service.run(
        RunSearchRequest(
            question=question,
            profile_id=settings.profile,
            offline=args.offline,
        ),
        progress=None if args.quiet else _ConsoleProgress(),
    )

    print(f"\nProfile: {response.profile_id}  |  Mode: {response.mode}  |  Run: {response.run_id}")
    print(f"Question: {response.question}")
    print(f"Found {response.counts.get('found', 0)} papers, selected {response.counts.get('selected', 0)}.")
    print(f"Sources used: {', '.join(response.apis_used) or 'none'}")
    available = [item.profile_id for item in profile_service.list_profiles()]
    if available:
        print(f"(Available profiles: {', '.join(available)})")
    print("\nTop selected papers:")
    selected = [paper for paper in response.papers if paper.get("selected")]
    for item in selected[:10]:
        print(
            f"  [{float(item.get('relevance_percent', 0.0)):5.1f}%] "
            f"{str(item.get('bucket', '')):<28} {str(item.get('title', ''))[:70]}"
        )
    if response.errors:
        print(f"\n{len(response.errors)} warning(s) recorded (non-fatal).")

    if args.json:
        args.json.write_text(json.dumps(response.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
