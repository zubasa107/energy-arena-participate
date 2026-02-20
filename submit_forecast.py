#!/usr/bin/env python3
"""
Submit a day-ahead forecast to the Energy Arena — one script, run locally.

Uses ENTSO-E data: d-1 actuals for price, d-2 actuals for load and solar.
Timestamps are shifted to the target date and POSTed to the Arena.

Usage:
  1. Set ENTSOE_API_KEY and ARENA_API_KEY (or pass --api_key).
  2. Run:

  python submit_forecast.py --target_date 21-02-2026 --challenge_id day_ahead_price --area DE_LU

  python submit_forecast.py --target_date 21-02-2026 --challenge_id day_ahead_load --area DE_LU
  python submit_forecast.py --target_date 21-02-2026 --challenge_id day_ahead_solar --area DE_LU

  python submit_forecast.py --target_date 21-02-2026 --dry_run   # print payload, do not submit

Forecasting logic (aligned with BAREF submit_d1_forecast):
  - day_ahead_price: ENTSO-E d-1 day-ahead prices → shift to target date.
  - day_ahead_load:  ENTSO-E d-2 actual load    → shift to target date.
  - day_ahead_solar: ENTSO-E d-2 actual solar   → shift to target date.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from entsoe import EntsoePandasClient

# Challenge id -> (entsoe_method, production_type for query_generation or None, lookback_days)
# Price: d-1; load and solar: d-2
CHALLENGE_ENTSOE = {
    "day_ahead_price": ("query_day_ahead_prices", None, 1),
    "day_ahead_load": ("query_load", None, 2),
    "day_ahead_solar": ("query_generation", "Solar - Actual Aggregated", 2),
}

ALLOWED_AREAS = ["DE_LU", "AT"]
TZ_NAME = "Europe/Berlin"


def parse_target_date(s: str) -> date:
    """Parse DD-MM-YYYY to date."""
    parts = s.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"target_date must be DD-MM-YYYY, got {s!r}")
    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    return date(year, month, day)


def _extract_series_from_result(
    result: Any,
    method_name: str,
    production_type: Optional[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Convert ENTSO-E client result to a single pd.Series for [start, end)."""
    if isinstance(result, pd.DataFrame) and isinstance(result.columns, pd.MultiIndex):
        result = result.copy()
        result.columns = [
            " - ".join(str(c) for c in col if str(c) != "") if isinstance(col, tuple) else str(col)
            for col in result.columns
        ]

    if isinstance(result, pd.DataFrame):
        if len(result.columns) == 1 and production_type is None:
            series = result.squeeze()
            if isinstance(series, pd.DataFrame):
                series = result.iloc[:, 0]
        elif production_type is None:
            raise ValueError(
                f"Method {method_name} returned DataFrame with columns: {list(result.columns)}. "
                "Specify production_type for query_generation."
            )
        elif production_type not in result.columns:
            raise ValueError(
                f"Production type '{production_type}' not in {list(result.columns)}"
            )
        else:
            series = result[production_type].squeeze()
    else:
        series = result

    if not isinstance(series, pd.Series):
        if isinstance(series, pd.DataFrame) and series.shape[1] == 1:
            series = series.iloc[:, 0]
        else:
            raise RuntimeError(f"Expected pd.Series from {method_name}, got {type(series)}")

    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index)
    if isinstance(series.index, pd.MultiIndex):
        raise RuntimeError("Series has MultiIndex, not supported")
    series = series.sort_index()
    series = series[(series.index >= start) & (series.index < end)]
    return series


def fetch_entsoe_series(
    api_key: str,
    entsoe_method: str,
    area: str,
    delivery_date: date,
    tz: str = TZ_NAME,
    production_type: Optional[str] = None,
) -> pd.Series:
    """Fetch one day of ENTSO-E data. Returns empty Series if data missing or has NaN/inf."""
    client = EntsoePandasClient(api_key=api_key)
    start_ts = pd.Timestamp(delivery_date, tz=tz)
    end_ts = start_ts + pd.Timedelta(days=1)
    method = getattr(client, entsoe_method, None)
    if method is None:
        raise RuntimeError(f"EntsoePandasClient has no method {entsoe_method!r}")

    result = method(country_code=area, start=start_ts, end=end_ts)
    series = _extract_series_from_result(result, entsoe_method, production_type, start_ts, end_ts)
    series = series.replace([float("inf"), float("-inf")], float("nan")).dropna()
    return series


def build_payload_from_entsoe(
    target_date: date,
    challenge_id: str,
    area: str,
    entsoe_api_key: str,
    tz_name: str = TZ_NAME,
) -> dict:
    """
    Fetch ENTSO-E data (d-1 for price, d-2 for load/solar), shift to target_date, build payload.
    """
    if challenge_id not in CHALLENGE_ENTSOE:
        raise ValueError(f"Unknown challenge_id: {challenge_id}")

    entsoe_method, production_type, lookback_days = CHALLENGE_ENTSOE[challenge_id]
    delivery_date = target_date - timedelta(days=lookback_days)

    series = fetch_entsoe_series(
        api_key=entsoe_api_key,
        entsoe_method=entsoe_method,
        area=area,
        delivery_date=delivery_date,
        tz=tz_name,
        production_type=production_type,
    )
    if series.empty:
        raise RuntimeError(
            f"No ENTSO-E data for {challenge_id}/{area} on {delivery_date} (d-{lookback_days}). "
            "Data may not be published yet."
        )

    tz = ZoneInfo(tz_name)
    delta = timedelta(days=lookback_days)
    points = []
    for ts, value in series.items():
        if hasattr(ts, "to_pydatetime"):
            ts_dt = ts.to_pydatetime()
        else:
            ts_dt = datetime.fromisoformat(str(ts))
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=tz)
        new_ts = ts_dt + delta
        points.append({"ts": new_ts.isoformat(), "value": float(value)})
    points.sort(key=lambda p: p["ts"])

    target_start = datetime(
        target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz
    )
    return {
        "challenge_id": challenge_id,
        "area": area,
        "target_start": target_start.isoformat(),
        "points": points,
    }


def submit(
    payload: dict,
    api_key: str,
    api_base: str,
    dry_run: bool = False,
    verbose: bool = True,
) -> bool:
    """POST payload to Arena submissions API. Returns True on success."""
    if dry_run:
        if verbose:
            import json
            print("Payload (dry run):")
            print(json.dumps(payload, indent=2))
        return True

    url = f"{api_base.rstrip('/')}/api/v1/submissions"
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        if verbose:
            data = resp.json()
            print(f"OK -> submission_id={data.get('submission_id')}")
        return True
    except requests.RequestException as e:
        if verbose:
            print(f"Submit failed: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit a day-ahead forecast to the Energy Arena (ENTSO-E d-1/d-2 persistence)."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        required=True,
        help="Target day in DD-MM-YYYY (e.g. 21-02-2026).",
    )
    parser.add_argument(
        "--challenge_id",
        type=str,
        default="day_ahead_price",
        choices=["day_ahead_price", "day_ahead_load", "day_ahead_solar"],
        help="Challenge code (default: day_ahead_price).",
    )
    parser.add_argument(
        "--area",
        type=str,
        default="DE_LU",
        choices=ALLOWED_AREAS,
        help="Bidding zone (default: DE_LU).",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=os.environ.get("ARENA_API_KEY", ""),
        help="Arena API key (or set ARENA_API_KEY).",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=os.environ.get("ARENA_API_BASE_URL", "https://api.energy-arena.org"),
        help="Arena API base URL.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Build and print payload only; do not submit.",
    )
    args = parser.parse_args()

    entsoe_key = os.environ.get("ENTSOE_API_KEY", "")
    if not entsoe_key:
        print("Error: ENTSOE_API_KEY must be set for fetching ENTSO-E data.", file=sys.stderr)
        sys.exit(1)
    if not args.api_key and not args.dry_run:
        print("Error: Arena API key required. Set ARENA_API_KEY or pass --api_key.", file=sys.stderr)
        sys.exit(1)

    try:
        target_date = parse_target_date(args.target_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _, _, lookback = CHALLENGE_ENTSOE[args.challenge_id]
    print(
        f"Target date: {target_date} | challenge: {args.challenge_id} | area: {args.area} | "
        f"ENTSO-E d-{lookback}"
    )

    try:
        payload = build_payload_from_entsoe(
            target_date=target_date,
            challenge_id=args.challenge_id,
            area=args.area,
            entsoe_api_key=entsoe_key,
        )
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        if not str(e).strip():
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    ok = submit(
        payload=payload,
        api_key=args.api_key,
        api_base=args.api_base,
        dry_run=args.dry_run,
        verbose=True,
    )
    if not ok and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
