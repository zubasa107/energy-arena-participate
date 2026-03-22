#!/usr/bin/env python3
"""
Submit a day-ahead forecast to the Energy Arena from a local machine.

Point forecast logic:
  - day_ahead_price: d-1 ENTSO-E day-ahead prices
  - day_ahead_load: d-2 ENTSO-E actual load
  - day_ahead_solar: d-2 ENTSO-E actual solar generation
  - day_ahead_wind: d-2 ENTSO-E actual onshore wind generation

Optional probabilistic extension:
  - --include_quantiles: append quantile forecasts estimated from historical
    analog values.
  - --include_ensemble: append quantile forecasts plus ensemble members
    estimated from the same historical analog values.

The probabilistic history pattern mirrors the current naive benchmark:
  - price/load: weekly analogs (d-7, d-14, d-21, ...)
  - solar/wind: daily submission-aware analogs (d-2, d-3, d-4, ...)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from entsoe import EntsoePandasClient

from challenge_catalog import get_active_challenge_lookup, get_challenge_infos


CHALLENGE_ENTSOE: Dict[str, Dict[str, Any]] = {
    "day_ahead_price": {
        "entsoe_method": "query_day_ahead_prices",
        "production_type": None,
        "point_lookback_days": 1,
        "history_start_lookback_days": 7,
        "history_step_days": 7,
        "history_count": 20,
        "fallback_quantiles": [0.025, 0.25, 0.5, 0.75, 0.975],
        "fallback_max_ensemble_size": 10,
    },
    "day_ahead_load": {
        "entsoe_method": "query_load",
        "production_type": None,
        "point_lookback_days": 2,
        "history_start_lookback_days": 7,
        "history_step_days": 7,
        "history_count": 20,
        "fallback_quantiles": [0.025, 0.25, 0.5, 0.75, 0.975],
        "fallback_max_ensemble_size": 10,
    },
    "day_ahead_solar": {
        "entsoe_method": "query_generation",
        "production_type": "Solar - Actual Aggregated",
        "point_lookback_days": 2,
        "history_start_lookback_days": 2,
        "history_step_days": 1,
        "history_count": 20,
        "fallback_quantiles": [0.025, 0.25, 0.5, 0.75, 0.975],
        "fallback_max_ensemble_size": 10,
    },
    "day_ahead_wind": {
        "entsoe_method": "query_generation",
        "production_type": "Wind Onshore - Actual Aggregated",
        "point_lookback_days": 2,
        "history_start_lookback_days": 2,
        "history_step_days": 1,
        "history_count": 20,
        "fallback_quantiles": [0.025, 0.25, 0.5, 0.75, 0.975],
        "fallback_max_ensemble_size": 10,
    },
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


def fetch_challenge_detail(api_base: str, challenge_id: str) -> Optional[dict]:
    """
    Fetch public challenge metadata from the Energy-Arena API.

    If this fails, the script falls back to the local mapping above.
    """
    url = f"{api_base.rstrip('/')}/api/v1/challenges/{challenge_id}"
    try:
        response = requests.get(url, timeout=20)
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    try:
        body = response.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def get_probabilistic_settings(
    challenge_id: str,
    api_base: str,
) -> tuple[List[float], int]:
    """
    Get quantiles and ensemble size from the challenge API if available.
    """
    challenge_cfg = CHALLENGE_ENTSOE[challenge_id]
    fallback_quantiles = [float(q) for q in challenge_cfg.get("fallback_quantiles", [])]
    fallback_max_ensemble_size = int(
        challenge_cfg.get("fallback_max_ensemble_size", 0) or 0
    )

    detail = fetch_challenge_detail(api_base, challenge_id)
    if not detail:
        return fallback_quantiles, fallback_max_ensemble_size

    pf_cfg = detail.get("probabilistic_forecast") or {}
    raw_quantiles = pf_cfg.get("quantiles") or fallback_quantiles
    raw_max_ensemble_size = pf_cfg.get("max_ensemble_size", fallback_max_ensemble_size)

    quantiles: List[float] = []
    for q in raw_quantiles:
        try:
            quantiles.append(float(q))
        except (TypeError, ValueError):
            continue
    quantiles = sorted(quantiles)

    try:
        max_ensemble_size = int(raw_max_ensemble_size or 0)
    except (TypeError, ValueError):
        max_ensemble_size = fallback_max_ensemble_size

    return quantiles, max(0, max_ensemble_size)


def print_open_challenge_infos(challenge_infos: Dict[str, Any]) -> None:
    """
    Pretty-print the open challenge metadata returned by the API.
    """
    active = challenge_infos.get("active_challenges") or []
    if not active:
        print("No open challenges are currently reported by the API.")
        return

    generated_at = challenge_infos.get("generated_at")
    if generated_at:
        print(f"Open challenge metadata generated at: {generated_at}")
        print()

    for entry in active:
        if not isinstance(entry, dict):
            continue

        challenge_id = str(entry.get("challenge_id", "unknown"))
        challenge_name = str(entry.get("challenge_name", challenge_id))
        areas = entry.get("areas") or []
        deadline = entry.get("next_submission_deadline") or "unknown"
        target_start = entry.get("next_target_start") or "unknown"
        supported = "yes" if challenge_id in CHALLENGE_ENTSOE else "no"

        print(f"{challenge_id} ({challenge_name})")
        print(f"  starter repo support: {supported}")
        print(f"  areas: {', '.join(str(area) for area in areas) if areas else '-'}")
        print(f"  next submission deadline: {deadline}")
        print(f"  next target start: {target_start}")

        payload_example = entry.get("payload_example")
        if isinstance(payload_example, dict):
            print("  payload example:")
            print(json.dumps(payload_example, indent=2))
        print()


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
            " - ".join(str(c) for c in col if str(c) != "")
            if isinstance(col, tuple)
            else str(col)
            for col in result.columns
        ]

    if isinstance(result, pd.DataFrame):
        if len(result.columns) == 1 and production_type is None:
            series = result.squeeze()
            if isinstance(series, pd.DataFrame):
                series = result.iloc[:, 0]
        elif production_type is None:
            raise ValueError(
                f"Method {method_name} returned DataFrame with columns: "
                f"{list(result.columns)}. Specify production_type for query_generation."
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
            raise RuntimeError(
                f"Expected pd.Series from {method_name}, got {type(series)}"
            )

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
    """Fetch one day of ENTSO-E data. Returns empty Series if missing."""
    client = EntsoePandasClient(api_key=api_key)
    start_ts = pd.Timestamp(delivery_date, tz=tz)
    end_ts = start_ts + pd.Timedelta(days=1)
    method = getattr(client, entsoe_method, None)
    if method is None:
        raise RuntimeError(f"EntsoePandasClient has no method {entsoe_method!r}")

    result = method(country_code=area, start=start_ts, end=end_ts)
    series = _extract_series_from_result(
        result, entsoe_method, production_type, start_ts, end_ts
    )
    series = series.replace([float("inf"), float("-inf")], float("nan")).dropna()
    return series


def _series_to_shifted_points(
    series: pd.Series,
    lookback_days: int,
    tz_name: str,
) -> List[Dict[str, float | str]]:
    """
    Shift a fetched ENTSO-E series forward to the target date grid.
    """
    tz = ZoneInfo(tz_name)
    delta = timedelta(days=lookback_days)
    points: List[Dict[str, float | str]] = []

    for ts, value in series.items():
        if hasattr(ts, "to_pydatetime"):
            ts_dt = ts.to_pydatetime()
        else:
            ts_dt = datetime.fromisoformat(str(ts))
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=tz)
        new_ts = ts_dt + delta
        points.append({"ts": new_ts.isoformat(), "value": float(value)})

    points.sort(key=lambda p: str(p["ts"]))
    return points


def collect_probabilistic_history_samples(
    target_date: date,
    challenge_id: str,
    area: str,
    entsoe_api_key: str,
    tz_name: str = TZ_NAME,
) -> Dict[str, List[float]]:
    """
    Collect historical analog values per target timestamp.
    """
    challenge_cfg = CHALLENGE_ENTSOE[challenge_id]
    entsoe_method = str(challenge_cfg["entsoe_method"])
    production_type = challenge_cfg.get("production_type")
    start_lookback_days = int(challenge_cfg["history_start_lookback_days"])
    step_days = int(challenge_cfg["history_step_days"])
    history_count = int(challenge_cfg["history_count"])

    history_by_ts: Dict[str, List[float]] = {}
    for i in range(history_count):
        lookback_days = start_lookback_days + i * step_days
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
            continue

        for point in _series_to_shifted_points(series, lookback_days, tz_name):
            ts = str(point["ts"])
            history_by_ts.setdefault(ts, []).append(float(point["value"]))

    return history_by_ts


def attach_probabilistic_vectors(
    points: List[Dict[str, float | str]],
    quantiles: List[float],
    max_ensemble_size: int,
    history_by_ts: Dict[str, List[float]],
    include_quantiles: bool,
    include_ensemble: bool,
) -> List[Dict[str, float | str | List[float]]]:
    """
    Convert point forecast entries into [pf, q1, ..., qN, e1, ..., eM].
    """
    include_quantiles = include_quantiles or include_ensemble
    ensemble_size = max_ensemble_size if include_ensemble else 0

    if not include_quantiles and ensemble_size <= 0:
        return points

    out: List[Dict[str, float | str | List[float]]] = []
    for point in points:
        pf = float(point["value"])
        ts = str(point["ts"])
        history_values = history_by_ts.get(ts, [])

        if include_quantiles and quantiles:
            if history_values:
                q_vals = np.quantile(
                    np.array(history_values, dtype=float), quantiles
                ).tolist()
            else:
                q_vals = [pf for _ in quantiles]
        else:
            q_vals = []

        if ensemble_size > 0:
            if history_values:
                ensemble_vals = [float(v) for v in history_values[:ensemble_size]]
                if len(ensemble_vals) < ensemble_size:
                    pad_value = ensemble_vals[-1] if ensemble_vals else pf
                    ensemble_vals.extend(
                        [float(pad_value)] * (ensemble_size - len(ensemble_vals))
                    )
            else:
                ensemble_vals = [pf for _ in range(ensemble_size)]
        else:
            ensemble_vals = []

        out.append(
            {
                "ts": ts,
                "value": [pf, *[float(v) for v in q_vals], *ensemble_vals],
            }
        )

    return out


def build_payload_from_entsoe(
    target_date: date,
    challenge_id: str,
    area: str,
    entsoe_api_key: str,
    api_base: str = "https://api.energy-arena.org",
    include_quantiles: bool = False,
    include_ensemble: bool = False,
    tz_name: str = TZ_NAME,
) -> dict:
    """
    Fetch ENTSO-E data, shift to target_date, and build a submission payload.
    """
    if challenge_id not in CHALLENGE_ENTSOE:
        raise ValueError(f"Unknown challenge_id: {challenge_id}")

    challenge_cfg = CHALLENGE_ENTSOE[challenge_id]
    entsoe_method = str(challenge_cfg["entsoe_method"])
    production_type = challenge_cfg.get("production_type")
    lookback_days = int(challenge_cfg["point_lookback_days"])
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

    points = _series_to_shifted_points(series, lookback_days, tz_name)

    if include_quantiles or include_ensemble:
        quantiles, max_ensemble_size = get_probabilistic_settings(
            challenge_id=challenge_id,
            api_base=api_base,
        )
        history_by_ts = collect_probabilistic_history_samples(
            target_date=target_date,
            challenge_id=challenge_id,
            area=area,
            entsoe_api_key=entsoe_api_key,
            tz_name=tz_name,
        )
        points = attach_probabilistic_vectors(
            points=points,
            quantiles=quantiles,
            max_ensemble_size=max_ensemble_size,
            history_by_ts=history_by_ts,
            include_quantiles=include_quantiles,
            include_ensemble=include_ensemble,
        )

    tz = ZoneInfo(tz_name)
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
    """POST payload to the Arena submissions API. Returns True on success."""
    if dry_run:
        if verbose:
            import json

            print("Payload (dry run):")
            print(json.dumps(payload, indent=2))
        return True

    def _extract_error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except Exception:
            return response.text.strip()

        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, str):
                return detail.strip()
            if isinstance(detail, list):
                messages = []
                for item in detail:
                    if isinstance(item, dict):
                        loc = ".".join(
                            str(x) for x in item.get("loc", []) if str(x) != "body"
                        )
                        msg = str(item.get("msg", "")).strip()
                        if loc and msg:
                            messages.append(f"{loc}: {msg}")
                        elif msg:
                            messages.append(msg)
                        else:
                            messages.append(str(item))
                    else:
                        messages.append(str(item))
                return "; ".join(messages).strip()
            if detail is not None:
                return str(detail).strip()
            return str(body).strip()

        return str(body).strip()

    _TRANSIENT_STATUS_CODES = {429, 502, 503, 504}
    _RETRY_DELAYS = [5, 15, 30]  # seconds between attempts 1→2, 2→3, 3→4

    url = f"{api_base.rstrip('/')}/api/v1/submissions"
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    last_message = ""
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            if verbose:
                print(
                    f"  Retrying in {delay}s (attempt {attempt}/{1 + len(_RETRY_DELAYS)})..."
                )
            time.sleep(delay)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.ok:
                if verbose:
                    data = resp.json()
                    print(f"OK -> submission_id={data.get('submission_id')}")
                return True

            detail = _extract_error_detail(resp)
            last_message = f"HTTP {resp.status_code}" + (
                f" - {detail}" if detail else ""
            )

            if resp.status_code not in _TRANSIENT_STATUS_CODES:
                break  # permanent error, no point retrying

            if verbose:
                print(f"  Transient error: {last_message}", file=sys.stderr)

        except requests.RequestException as e:
            last_message = str(e)
            if verbose:
                print(f"  Connection error: {last_message}", file=sys.stderr)

    if verbose:
        print(f"Submit failed: {last_message}", file=sys.stderr)
    return False


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Submit a day-ahead forecast to the Energy Arena."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        default=None,
        help="Target day in DD-MM-YYYY (e.g. 21-02-2026). Required unless --list_open_challenges is used.",
    )
    parser.add_argument(
        "--challenge_id",
        type=str,
        default="day_ahead_price",
        choices=list(CHALLENGE_ENTSOE),
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
        default=local_env.get("ARENA_API_KEY", "").strip(),
        help="Arena API key (default: local .env ARENA_API_KEY).",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=(
            local_env.get("ARENA_API_BASE_URL", "")
            or os.environ.get("ARENA_API_BASE_URL", "")
            or "https://api.energy-arena.org"
        ).strip(),
        help="Arena API base URL.",
    )
    parser.add_argument(
        "--use_global_env",
        action="store_true",
        help="Allow fallback to globally set ENTSOE_API_KEY/ARENA_API_KEY if missing in local .env.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Build and print payload only; do not submit.",
    )
    parser.add_argument(
        "--list_open_challenges",
        action="store_true",
        help="Fetch open challenge metadata from the Energy Arena API and exit.",
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

    entsoe_key = local_env.get("ENTSOE_API_KEY", "").strip()
    arena_key = (args.api_key or "").strip()
    if args.use_global_env:
        entsoe_key = entsoe_key or os.environ.get("ENTSOE_API_KEY", "").strip()
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()

    if args.list_open_challenges:
        try:
            challenge_infos = get_challenge_infos(
                args.api_base,
                arena_api_key=arena_key or None,
            )
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
        print_open_challenge_infos(challenge_infos)
        return

    if not entsoe_key:
        print(
            "Error: ENTSOE_API_KEY must be set in local .env "
            "(or use --use_global_env).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not arena_key and not args.dry_run:
        print(
            "Error: Arena API key required. Set ARENA_API_KEY in local .env, "
            "pass --api_key, or use --use_global_env.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.target_date:
        print(
            "Error: --target_date is required unless --list_open_challenges is used.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        target_date = parse_target_date(args.target_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    lookback = int(CHALLENGE_ENTSOE[args.challenge_id]["point_lookback_days"])
    probabilistic_mode = []
    if args.include_quantiles or args.include_ensemble:
        probabilistic_mode.append("quantiles")
    if args.include_ensemble:
        probabilistic_mode.append("ensemble")
    mode_suffix = (
        " | probabilistic: " + ", ".join(probabilistic_mode)
        if probabilistic_mode
        else ""
    )
    print(
        f"Target date: {target_date} | challenge: {args.challenge_id} | area: {args.area} | "
        f"ENTSO-E d-{lookback}{mode_suffix}"
    )

    try:
        active_lookup = get_active_challenge_lookup(
            args.api_base,
            arena_api_key=arena_key or None,
        )
    except Exception as e:
        print(
            f"Warning: failed to fetch open challenge metadata: {e}",
            file=sys.stderr,
        )
    else:
        current_info = active_lookup.get(args.challenge_id)
        if current_info is None:
            print(
                f"Warning: challenge '{args.challenge_id}' is not currently listed by /api/v1/challenges/open.",
                file=sys.stderr,
            )
        else:
            active_areas = current_info.get("areas") or []
            if args.area not in active_areas:
                print(
                    f"Warning: area '{args.area}' is not currently listed for challenge '{args.challenge_id}'. "
                    f"API areas: {active_areas}",
                    file=sys.stderr,
                )
            else:
                next_deadline = current_info.get("next_submission_deadline")
                next_target_start = current_info.get("next_target_start")
                if next_deadline and next_target_start:
                    print(
                        f"API metadata: next deadline {next_deadline} | next target start {next_target_start}"
                    )

    try:
        payload = build_payload_from_entsoe(
            target_date=target_date,
            challenge_id=args.challenge_id,
            area=args.area,
            entsoe_api_key=entsoe_key,
            api_base=args.api_base,
            include_quantiles=args.include_quantiles,
            include_ensemble=args.include_ensemble,
        )
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        if not str(e).strip():
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    ok = submit(
        payload=payload,
        api_key=arena_key,
        api_base=args.api_base,
        dry_run=args.dry_run,
        verbose=True,
    )
    if not ok and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
