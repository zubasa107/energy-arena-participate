#!/usr/bin/env python3
"""
Load the source ENTSO-E data used by the starter model for one target date.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timezone, timedelta
from pathlib import Path

from submit_forecast import (
    DEFAULT_API_BASE,
    TARGET_BASELINES,
    _load_local_env_values,
    _resolve_challenge_context,
    fetch_entsoe_series,
    parse_target_date,
)


def _series_to_points(series) -> list[dict]:
    points = []
    for ts, value in series.sort_index().items():
        ts_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        points.append({"ts": ts_dt.isoformat(), "value": float(value)})
    return points


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Load the source ENTSO-E data used by the starter model."
    )
    parser.add_argument("--target_date", type=str, required=True, help="Target day in DD-MM-YYYY.")
    parser.add_argument("--challenge_id", type=str, required=True, help="Challenge id.")
    parser.add_argument("--area", type=str, default="", help="Optional area override.")
    parser.add_argument(
        "--api_key",
        type=str,
        default=local_env.get("ARENA_API_KEY", "").strip(),
        help="Arena API key (default: local .env ARENA_API_KEY).",
    )
    parser.add_argument(
        "--entsoe_api_key",
        type=str,
        default=local_env.get("ENTSOE_API_KEY", "").strip(),
        help="ENTSO-E API key (default: local .env ENTSOE_API_KEY).",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=(
            local_env.get("ARENA_API_BASE_URL", "")
            or os.environ.get("ARENA_API_BASE_URL", "")
            or DEFAULT_API_BASE
        ).strip(),
        help="Arena API base URL.",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="loaded_entsoe_data.json",
        help="Path to the saved source-data JSON (default: loaded_entsoe_data.json).",
    )
    args = parser.parse_args()

    entsoe_key = (args.entsoe_api_key or "").strip()
    if not entsoe_key:
        print("Error: ENTSOE_API_KEY is required for ENTSO-E source loading.", file=sys.stderr)
        sys.exit(1)

    try:
        target_date = parse_target_date(args.target_date)
        context = _resolve_challenge_context(
            api_base=args.api_base,
            challenge_id=args.challenge_id,
            area=args.area or None,
            arena_api_key=(args.api_key or "").strip() or None,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if context.target_code not in TARGET_BASELINES:
        print(
            f"Error: target '{context.target_code}' is not supported by the built-in starter model.",
            file=sys.stderr,
        )
        sys.exit(1)

    lookback_days = int(TARGET_BASELINES[context.target_code]["point_lookback_days"])
    delivery_date = target_date - timedelta(days=lookback_days)

    try:
        series = fetch_entsoe_series(
            api_key=entsoe_key,
            context=context,
            delivery_date=delivery_date,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output = {
        "source": "entsoe",
        "challenge_id": context.challenge_id,
        "target_name": context.target_name,
        "area": context.area,
        "delivery_date": delivery_date.isoformat(),
        "lookback_days": lookback_days,
        "points": _series_to_points(series),
    }

    output_path = Path(args.output_path).expanduser()
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Saved ENTSO-E source data to {output_path.resolve()}")


if __name__ == "__main__":
    main()
