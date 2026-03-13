#!/usr/bin/env python3
"""
Run daily submissions for all configured challenges and both areas.

Default target date: tomorrow in Europe/Berlin, so running around 11:30 local
time submits before the 12:00 deadline for day-ahead challenges.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Same directory as this script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from submit_forecast import (  # noqa: E402
    ALLOWED_AREAS,
    CHALLENGE_ENTSOE,
    build_payload_from_entsoe,
    submit,
)

TZ_NAME = "Europe/Berlin"


def tomorrow_cet() -> date:
    """Tomorrow's date in Europe/Berlin."""
    from datetime import datetime

    tz = ZoneInfo(TZ_NAME)
    now = datetime.now(tz).date()
    return now + timedelta(days=1)


def target_date_to_dd_mm_yyyy(d: date) -> str:
    """Format date as DD-MM-YYYY."""
    return d.strftime("%d-%m-%Y")


def _load_env_file(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _load_local_env_values() -> dict:
    repo_root = Path(__file__).resolve().parent
    return _load_env_file(repo_root / ".env")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit forecasts for all challenges and areas."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        default=None,
        help="Target day DD-MM-YYYY (default: tomorrow in Europe/Berlin).",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Build payloads only; do not submit.",
    )
    parser.add_argument(
        "--use_global_env",
        action="store_true",
        help="Allow fallback to globally set ENTSOE_API_KEY/ARENA_API_KEY if missing in local .env.",
    )
    parser.add_argument(
        "--include_quantiles",
        action="store_true",
        help="Append quantiles estimated from historical analog values.",
    )
    parser.add_argument(
        "--include_ensemble",
        action="store_true",
        help="Append quantiles plus ensemble members estimated from historical analog values.",
    )
    args = parser.parse_args()

    local_env = _load_local_env_values()
    entsoe_key = local_env.get("ENTSOE_API_KEY", "").strip()
    arena_key = local_env.get("ARENA_API_KEY", "").strip()
    api_base = (
        local_env.get("ARENA_API_BASE_URL", "")
        or os.environ.get("ARENA_API_BASE_URL", "")
        or "https://api.energy-arena.org"
    ).strip()

    if args.use_global_env:
        entsoe_key = entsoe_key or os.environ.get("ENTSOE_API_KEY", "").strip()
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()

    if not entsoe_key:
        print(
            "Error: ENTSOE_API_KEY must be set in local .env "
            "(or use --use_global_env).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not arena_key and not args.dry_run:
        print(
            "Error: ARENA_API_KEY must be set in local .env "
            "(or use --use_global_env / --dry_run).",
            file=sys.stderr,
        )
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
    mode_bits = []
    if args.include_quantiles or args.include_ensemble:
        mode_bits.append("quantiles")
    if args.include_ensemble:
        mode_bits.append("ensemble")
    mode_suffix = f" | probabilistic: {', '.join(mode_bits)}" if mode_bits else ""

    print(
        f"Target date: {target_date} ({target_str}) | challenges: {list(CHALLENGE_ENTSOE)} "
        f"| areas: {ALLOWED_AREAS}{mode_suffix}"
    )
    if args.dry_run:
        print("dry_run: no submissions will be sent.")
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
                    api_base=api_base,
                    include_quantiles=args.include_quantiles,
                    include_ensemble=args.include_ensemble,
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
