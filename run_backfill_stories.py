#!/usr/bin/env python3
"""One-shot CLI: backfill covered_stories from historical analysis_runs."""

from __future__ import annotations

import json
import logging

from src.db.covered_stories import backfill_covered_stories_from_analysis_runs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    result = backfill_covered_stories_from_analysis_runs()
    logger.info(
        "Backfill complete: scanned %s analysis run(s), found %s idea(s), inserted %s story row(s).",
        result["runs_scanned"],
        result["ideas_found"],
        result["stories_inserted"],
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
