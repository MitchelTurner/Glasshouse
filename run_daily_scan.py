#!/usr/bin/env python3
"""Run the daily new-meeting scan once (for cron or manual use)."""

from src.services.daily_scan import run_daily_scan


def main() -> None:
    result = run_daily_scan()
    print(result)


if __name__ == "__main__":
    main()
