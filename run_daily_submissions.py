#!/usr/bin/env python3
"""
Run daily submissions for all 3 challenges and 2 areas (6 submissions total).

Target date: tomorrow (Europe/Berlin) by default, so when run at 11:30 CET
you submit before the 12:00 deadline for that day.

Usage:
  Set ENTSOE_API_KEY and ARENA_API_KEY (or use .env); then:

  python run_daily_submissions.py
  python run_daily_submissions.py --target_date 22-02-2026
  python run_daily_submissions.py --dry_run

Schedule at 11:30 CET (Windows Task Scheduler or cron) to run this script.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from zoneinfo import ZoneInfo

# Same directory as this script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from submit_forecast import (
    ALLOWED_AREAS,
    CHALLENGE_ENTSOE,
    build_payload_from_entsoe,
    submit,
)

TZ_NAME = "Europe/Berlin"


def tomorrow_cet() -> date:
    """Tomorrow's date in Europe/Berlin (for 11:30 CET run, this is the target day)."""
    tz = ZoneInfo(TZ_NAME)
    from datetime import datetime
    now = datetime.now(tz).date()
    return now + timedelta(days=1)


def target_date_to_dd_mm_yyyy(d: date) -> str:
    """Format date as DD-MM-YYYY."""
    return d.strftime("%d-%m-%Y")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit forecasts for all challenges and areas (target = tomorrow by default)."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        default=None,
        help="Target day DD-MM-YYYY (default: tomorrow CET).",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Build payloads only; do not submit.",
    )
    args = parser.parse_args()

    entsoe_key = os.environ.get("ENTSOE_API_KEY", "")
    arena_key = os.environ.get("ARENA_API_KEY", "")
    api_base = os.environ.get("ARENA_API_BASE_URL", "https://api.energy-arena.org")

    if not entsoe_key:
        print("Error: ENTSOE_API_KEY must be set.", file=sys.stderr)
        sys.exit(1)
    if not arena_key and not args.dry_run:
        print("Error: ARENA_API_KEY must be set (or use --dry_run).", file=sys.stderr)
        sys.exit(1)

    if args.target_date:
        parts = args.target_date.strip().split("-")
        if len(parts) != 3:
            print("Error: --target_date must be DD-MM-YYYY.", file=sys.stderr)
            sys.exit(1)
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        target_date = date(year, month, day)
    else:
        target_date = tomorrow_cet()

    target_str = target_date_to_dd_mm_yyyy(target_date)
    print(f"Target date: {target_date} ({target_str}) | challenges: {list(CHALLENGE_ENTSOE)} | areas: {ALLOWED_AREAS}")
    if args.dry_run:
        print(" dry_run: no submissions will be sent.")
    print()

    ok_count = 0
    fail_count = 0
    for challenge_id in CHALLENGE_ENTSOE:
        for area in ALLOWED_AREAS:
            try:
                payload = build_payload_from_entsoe(
                    target_date=target_date,
                    challenge_id=challenge_id,
                    area=area,
                    entsoe_api_key=entsoe_key,
                )
                ok = submit(
                    payload=payload,
                    api_key=arena_key,
                    api_base=api_base,
                    dry_run=args.dry_run,
                    verbose=True,
                )
                if ok:
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print(f"  FAIL {challenge_id} {area}: {e}", file=sys.stderr)
                fail_count += 1

    print()
    print(f"Done: {ok_count} ok, {fail_count} failed (total {ok_count + fail_count})")
    if fail_count and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
