#!/usr/bin/env python3
"""One-shot CLI: analyze meetings and send video ideas via Telegram.

Defaults to new (unprocessed) meetings, or the latest few if everything
in the lookback window was already analyzed. Repeat ideas are filtered out.

Usage:
    python run_pipeline.py                 # new/latest + send Telegram
    python run_pipeline.py --dry-run       # preview without sending
    python run_pipeline.py --all-recent    # every meeting in LOOKBACK_DAYS
    python run_pipeline.py --latest        # newest meetings only
"""

from __future__ import annotations

import argparse

from src.config import get_settings
from src.services.pipeline import run_pipeline


def run(dry_run: bool | None = None, scope: str | None = None) -> int:
    settings = get_settings()
    if dry_run is not None:
        settings.dry_run = dry_run

    resolved_scope = scope or settings.analyze_scope
    print(f"Fetching meeting transcripts (scope={resolved_scope}, last {settings.lookback_days} days)...")
    try:
        result = run_pipeline(settings, dry_run=settings.dry_run, scope=resolved_scope)
    except ValueError as exc:
        print(str(exc))
        return 0

    print(f"Found {result.transcript_count} transcript(s).")
    print(f"Generated {result.idea_count} new idea(s).")
    if result.skipped_duplicate_count:
        print(f"Hidden {result.skipped_duplicate_count} already-covered idea(s).")
    print(f"Saved full analysis to {result.output_path}")

    if settings.dry_run:
        print("\n--- DRY RUN: Telegram message preview ---\n")
        print(
            result.telegram_preview.replace("<b>", "**")
            .replace("</b>", "**")
            .replace("<i>", "_")
            .replace("</i>", "_")
        )
    elif result.telegram_sent:
        print("Telegram notification sent.")
    else:
        print("Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID).")
        print("\n--- Message preview ---\n")
        print(result.telegram_preview)

    if result.run_id is not None:
        print(f"Recorded analysis run #{result.run_id}.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Meeting transcript → video ideas → Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Skip Telegram, print preview")
    parser.add_argument(
        "--all-recent",
        action="store_true",
        help="Analyze every meeting in LOOKBACK_DAYS instead of new/latest only",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Analyze only the newest meetings",
    )
    args = parser.parse_args()
    scope = "recent" if args.all_recent else "latest" if args.latest else None
    return run(dry_run=args.dry_run, scope=scope)


if __name__ == "__main__":
    raise SystemExit(main())
