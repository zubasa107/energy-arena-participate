#!/usr/bin/env python3
"""
Legacy combined helper: generate one forecast payload and submit it to Energy
Arena from a local machine.

Default baseline source:
  - SMARD public market data (no extra key required)

Optional advanced baseline source:
  - ENTSO-E Transparency Platform via ENTSOE_API_KEY

The script resolves the selected challenge via the live Energy Arena API,
derives the required payload format from the challenge objective
(point / quantile / ensemble), and then builds a naive baseline forecast from
historical data for that target and area.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import inspect
import io
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from entsoe import EntsoePandasClient

from _challenge_catalog import (
    get_active_challenge_lookup,
    get_challenge_detail,
    get_challenge_infos,
)

SMARD_DOWNLOAD_URL = "https://www.smard.de/nip-download-manager/nip/download/market-data"
DEFAULT_API_BASE = "https://api.energy-arena.org"
DEFAULT_TIMEZONE = "Europe/Berlin"
SUPPORTED_DATA_SOURCES = {"smard", "entsoe"}

TARGET_BASELINES: Dict[str, Dict[str, Any]] = {
    "day_ahead_price": {
        "entsoe_method": "query_day_ahead_prices",
        "production_type": None,
        "point_lookback_days": 1,
        "history_start_lookback_days": 7,
        "history_step_days": 7,
        "history_count": 20,
    },
    "day_ahead_load": {
        "entsoe_method": "query_load",
        "production_type": None,
        "point_lookback_days": 2,
        "history_start_lookback_days": 7,
        "history_step_days": 7,
        "history_count": 20,
    },
    "day_ahead_solar": {
        "entsoe_method": "query_generation",
        "production_type": "Solar - Actual Aggregated",
        "point_lookback_days": 2,
        "history_start_lookback_days": 2,
        "history_step_days": 1,
        "history_count": 20,
    },
    "day_ahead_wind": {
        "entsoe_method": "query_generation",
        "production_type": "Wind Onshore - Actual Aggregated",
        "point_lookback_days": 2,
        "history_start_lookback_days": 2,
        "history_step_days": 1,
        "history_count": 20,
    },
}

_CUSTOM_MODEL_MODULE: Any | None = None
_CUSTOM_MODEL_LOAD_ATTEMPTED = False


@dataclass(frozen=True)
class SmardCounterpartSpec:
    module_id: int
    region: str
    resolution: str
    source_unit: str
    target_unit: str
    value_multiplier: float


@dataclass(frozen=True)
class ChallengeContext:
    challenge_id: str
    challenge_name: str
    target_code: str
    target_name: str
    area: str
    areas: List[str]
    forecast_objective: str
    accepted_forecast_format: str
    reference_timezone: str
    target_period_timezone: str
    target_period_type: str
    probabilistic_quantiles: List[float]
    max_ensemble_size: int
    smard_counterpart: SmardCounterpartSpec | None
    baseline_supported: bool
    challenge_detail: Dict[str, Any]


def parse_target_date(raw: str) -> date:
    parts = str(raw or "").strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"target_date must be DD-MM-YYYY, got {raw!r}")
    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    return date(year, month, day)


def _load_env_file(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _load_local_env_values() -> dict:
    repo_root = Path(__file__).resolve().parent
    return _load_env_file(repo_root / ".env")


def _normalized_data_source(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return "smard"
    if value not in SUPPORTED_DATA_SOURCES:
        raise ValueError(
            f"Unsupported data source {raw!r}. Choose one of: {sorted(SUPPORTED_DATA_SOURCES)}."
        )
    return value


def _get_default_data_source(local_env: dict) -> str:
    for key in ("BASELINE_DATA_SOURCE", "FORECAST_BASELINE_SOURCE", "DATA_SOURCE"):
        value = str(local_env.get(key, "")).strip()
        if value:
            return _normalized_data_source(value)
    return "smard"


def _normalize_float_list(values: Any) -> List[float]:
    out: List[float] = []
    for value in values or []:
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _resolve_forecast_objective(detail: Dict[str, Any]) -> str:
    raw = str(detail.get("forecast_objective") or "").strip().lower()
    if raw in {"point", "quantile", "ensemble"}:
        return raw
    return "point"


def _resolve_challenge_context(
    *,
    api_base: str,
    challenge_id: str,
    area: str | None,
    arena_api_key: str | None,
) -> ChallengeContext:
    detail = get_challenge_detail(
        api_base,
        challenge_id,
        arena_api_key=arena_api_key,
    )
    metadata = detail.get("catalog_metadata") or {}
    target_code = str(
        detail.get("target_code")
        or metadata.get("target_code")
        or ""
    ).strip()
    if not target_code:
        raise RuntimeError(
            f"Challenge {challenge_id} does not expose a target_code in the API."
        )

    areas = [str(item).strip() for item in (detail.get("areas") or []) if str(item).strip()]
    requested_area = str(area or "").strip()
    if requested_area:
        if areas and requested_area not in areas:
            raise RuntimeError(
                f"Area '{requested_area}' is not valid for challenge {challenge_id}. API areas: {areas}."
            )
        resolved_area = requested_area
    else:
        if len(areas) == 1:
            resolved_area = areas[0]
        elif metadata.get("area_code"):
            resolved_area = str(metadata["area_code"]).strip()
        else:
            raise RuntimeError(
                f"Challenge {challenge_id} exposes multiple/no areas. Please pass --area explicitly."
            )

    pf_cfg = detail.get("probabilistic_forecast") or {}
    smard_raw = detail.get("smard_counterpart") or None
    smard_spec = (
        SmardCounterpartSpec(
            module_id=int(smard_raw.get("module_id") or 0),
            region=str(smard_raw.get("region") or "").strip(),
            resolution=str(smard_raw.get("resolution") or "quarterhour").strip() or "quarterhour",
            source_unit=str(smard_raw.get("source_unit") or "").strip() or "MWh",
            target_unit=str(smard_raw.get("target_unit") or "").strip() or "MW",
            value_multiplier=float(smard_raw.get("value_multiplier") or 1.0),
        )
        if isinstance(smard_raw, dict) and smard_raw.get("module_id") and smard_raw.get("region")
        else None
    )

    return ChallengeContext(
        challenge_id=str(detail.get("code") or challenge_id).strip(),
        challenge_name=str(detail.get("name") or challenge_id).strip(),
        target_code=target_code,
        target_name=str(
            detail.get("target_name")
            or metadata.get("target_name")
            or target_code
        ).strip(),
        area=resolved_area,
        areas=areas or ([resolved_area] if resolved_area else []),
        forecast_objective=_resolve_forecast_objective(detail),
        accepted_forecast_format=str(
            detail.get("accepted_forecast_format")
            or detail.get("forecast_format_label")
            or metadata.get("forecast_format_label")
            or "-"
        ).strip(),
        reference_timezone=str(detail.get("reference_timezone") or DEFAULT_TIMEZONE).strip()
        or DEFAULT_TIMEZONE,
        target_period_timezone=str(
            (detail.get("target_period") or {}).get("timezone")
            or detail.get("reference_timezone")
            or DEFAULT_TIMEZONE
        ).strip()
        or DEFAULT_TIMEZONE,
        target_period_type=str(
            (detail.get("target_period") or {}).get("type") or "calendar_day"
        ).strip()
        or "calendar_day",
        probabilistic_quantiles=_normalize_float_list(pf_cfg.get("quantiles") or []),
        max_ensemble_size=max(0, int(pf_cfg.get("max_ensemble_size") or 0)),
        smard_counterpart=smard_spec,
        baseline_supported=target_code in TARGET_BASELINES,
        challenge_detail=detail,
    )


def print_open_challenge_infos(
    challenge_infos: Dict[str, Any],
    *,
    api_base: str,
    arena_api_key: str | None = None,
) -> None:
    active = challenge_infos.get("active_challenges") or []
    if not active:
        print("No open challenges are currently reported by the API.")
        return

    headers = (
        "Challenge ID",
        "Target",
        "Area",
        "Forecast Format",
        "Next Submission Deadline",
        "Next Target Start",
    )
    rows: List[tuple[str, str, str, str, str, str]] = []

    for entry in active:
        if not isinstance(entry, dict):
            continue
        challenge_id = str(entry.get("challenge_id") or "").strip()
        target_name = str(
            entry.get("target_name")
            or (entry.get("catalog_metadata") or {}).get("target_name")
            or entry.get("challenge_name")
            or challenge_id
        ).strip()
        areas = [str(area).strip() for area in (entry.get("areas") or []) if str(area).strip()]
        area_label = areas[0] if len(areas) == 1 else ", ".join(areas) if areas else "-"
        forecast_format = str(entry.get("accepted_forecast_format") or "-").strip()
        deadline = str(entry.get("next_submission_deadline") or "-").strip()
        target_start = str(entry.get("next_target_start") or "-").strip()

        rows.append(
            (
                challenge_id or "-",
                target_name or "-",
                area_label,
                forecast_format,
                deadline,
                target_start,
            )
        )

    widths = [
        max(len(header), *(len(row[idx]) for row in rows))
        for idx, header in enumerate(headers)
    ]
    format_row = "  ".join(f"{{:<{width}}}" for width in widths)
    print(format_row.format(*headers))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print(format_row.format(*row))


def save_payload_to_file(payload: dict, output_path: str) -> Path:
    ordered_keys = [
        "challenge_id",
        "area",
        "target_date",
        "target_start",
        "values",
        "points",
    ]
    ordered_payload = {
        key: payload[key] for key in ordered_keys if key in payload
    }
    for key, value in payload.items():
        if key not in ordered_payload:
            ordered_payload[key] = value

    path = Path(output_path).expanduser()
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ordered_payload, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def _load_custom_model_module() -> Any | None:
    global _CUSTOM_MODEL_MODULE
    global _CUSTOM_MODEL_LOAD_ATTEMPTED

    if _CUSTOM_MODEL_LOAD_ATTEMPTED:
        return _CUSTOM_MODEL_MODULE

    _CUSTOM_MODEL_LOAD_ATTEMPTED = True
    repo_root = Path(__file__).resolve().parent
    custom_model_path = repo_root / "custom_model.py"
    if not custom_model_path.exists() or not custom_model_path.is_file():
        _CUSTOM_MODEL_MODULE = None
        return None

    spec = importlib.util.spec_from_file_location(
        "energy_arena_custom_model",
        custom_model_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {custom_model_path.name}.")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(f"Failed to import {custom_model_path.name}: {exc}") from exc

    if not callable(getattr(module, "build_payload", None)) and not callable(
        getattr(module, "transform_payload", None)
    ):
        raise RuntimeError(
            f"{custom_model_path.name} must define build_payload(...) or transform_payload(...)."
        )

    _CUSTOM_MODEL_MODULE = module
    return module


def _call_hook(func: Callable[..., Any], **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return func(**kwargs)
    filtered = {
        key: value for key, value in kwargs.items() if key in signature.parameters
    }
    return func(**filtered)


def _validate_payload(payload: Any, *, source: str) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{source} must return a dictionary payload.")
    if "challenge_id" not in payload:
        raise RuntimeError(f"{source} returned a payload missing key: ['challenge_id']")
    has_points = "points" in payload
    has_values = "values" in payload
    if has_points == has_values:
        raise RuntimeError(
            f"{source} must return exactly one of payload['points'] or payload['values']."
        )
    if has_points and not isinstance(payload.get("points"), list):
        raise RuntimeError(f"{source} returned payload['points'] that is not a list.")
    if has_values and not isinstance(payload.get("values"), list):
        raise RuntimeError(f"{source} returned payload['values'] that is not a list.")
    return payload


def run_setup_check(
    *,
    entsoe_key: str,
    arena_key: str,
    api_base: str,
    data_source: str,
) -> int:
    repo_root = Path(__file__).resolve().parent
    env_path = repo_root / ".env"
    problems: List[str] = []

    print("Setup check")
    print(f"  repo folder: {repo_root}")
    print(f"  local .env: {'found' if env_path.exists() else 'missing'}")
    print(f"  baseline data source: {data_source}")
    print(f"  ARENA_API_KEY: {'ok' if arena_key else 'missing'}")
    print(f"  ENTSOE_API_KEY: {'ok (optional)' if entsoe_key else 'missing (optional)'}")
    print(f"  ARENA_API_BASE_URL: {api_base}")

    try:
        challenge_infos = get_challenge_infos(api_base, arena_api_key=arena_key or None)
    except Exception as exc:
        problems.append(f"Open challenge catalog unreachable: {exc}")
    else:
        active_count = len(challenge_infos.get("active_challenges") or [])
        print(f"  open challenge catalog: ok ({active_count} active challenge(s))")

    try:
        custom_model = _load_custom_model_module()
    except Exception as exc:
        problems.append(f"custom_model.py failed to load: {exc}")
    else:
        if custom_model is None:
            print("  custom_model.py: not configured (baseline builder will be used)")
        else:
            print("  custom_model.py: loaded")

    if not arena_key:
        problems.append("ARENA_API_KEY is missing.")
    if data_source == "entsoe" and not entsoe_key:
        problems.append("ENTSOE_API_KEY is required when baseline data source is 'entsoe'.")

    print()
    if problems:
        print("Problems found:")
        for item in problems:
            print(f"  - {item}")
        print()
        print("Suggested next steps:")
        print("  1. Copy .env.example to .env")
        print("  2. Fill ARENA_API_KEY")
        if data_source == "entsoe":
            print("  3. Fill ENTSOE_API_KEY or switch to --data_source smard")
        else:
            print("  3. Optionally add ENTSOE_API_KEY if you want --data_source entsoe")
        print("  4. Run python run_forecast_model.py --check_setup again")
        return 1

    print("Setup looks good.")
    print()
    print("Suggested next steps:")
    print("  1. python run_forecast_model.py --list_open_challenges")
    print(
        "  2. python run_forecast_model.py --target_date DD-MM-YYYY "
        "--challenge_id <challenge_id> --save_payload test_payload.json"
    )
    print(
        "  3. python submit_forecast_to_energy_arena.py --payload_path test_payload.json"
    )
    return 0


def _extract_series_from_result(
    result: Any,
    method_name: str,
    production_type: Optional[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
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
    return series.replace([float("inf"), float("-inf")], float("nan")).dropna()


def fetch_entsoe_series(
    *,
    api_key: str,
    context: ChallengeContext,
    delivery_date: date,
) -> pd.Series:
    if not api_key:
        raise RuntimeError("ENTSOE_API_KEY is required for --data_source entsoe.")
    if context.target_code not in TARGET_BASELINES:
        raise RuntimeError(
            f"Target '{context.target_code}' is not supported by the built-in ENTSO-E baseline."
        )

    challenge_cfg = TARGET_BASELINES[context.target_code]
    entsoe_method = str(challenge_cfg["entsoe_method"])
    production_type = challenge_cfg.get("production_type")
    tz_name = context.reference_timezone or DEFAULT_TIMEZONE

    client = EntsoePandasClient(api_key=api_key)
    start_ts = pd.Timestamp(delivery_date, tz=tz_name)
    end_ts = start_ts + pd.Timedelta(days=1)
    method = getattr(client, entsoe_method, None)
    if method is None:
        raise RuntimeError(f"EntsoePandasClient has no method {entsoe_method!r}")

    result = method(country_code=context.area, start=start_ts, end=end_ts)
    return _extract_series_from_result(
        result,
        entsoe_method,
        production_type,
        start_ts,
        end_ts,
    )


def _parse_smard_numeric(raw: str) -> float:
    text = raw.strip().replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def _parse_smard_local_timestamp(
    raw: str,
    *,
    local_tz: ZoneInfo,
    previous_utc: Optional[datetime],
) -> datetime:
    naive = datetime.strptime(raw.strip(), "%b %d, %Y %I:%M %p")
    candidates = sorted(
        {
            naive.replace(tzinfo=local_tz, fold=0).astimezone(timezone.utc),
            naive.replace(tzinfo=local_tz, fold=1).astimezone(timezone.utc),
        }
    )
    if previous_utc is None:
        return candidates[0]
    for candidate in candidates:
        if candidate > previous_utc:
            return candidate
    return candidates[-1]


def _parse_smard_csv_points(
    content: bytes,
    *,
    timezone_name: str,
    value_multiplier: float,
) -> list[dict]:
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    rows = list(reader)
    if len(rows) <= 1:
        return []

    local_tz = ZoneInfo(timezone_name)
    previous_ts: Optional[datetime] = None
    out: list[dict] = []

    for row in rows[1:]:
        if len(row) < 3:
            continue
        start_raw = (row[0] or "").strip()
        value_raw = (row[2] or "").strip()
        if not start_raw or not value_raw:
            continue
        try:
            ts_utc = _parse_smard_local_timestamp(
                start_raw,
                local_tz=local_tz,
                previous_utc=previous_ts,
            )
            value = _parse_smard_numeric(value_raw) * value_multiplier
        except (TypeError, ValueError):
            continue
        out.append({"ts": ts_utc, "value": float(value)})
        previous_ts = ts_utc

    return out


def fetch_smard_series(
    *,
    context: ChallengeContext,
    delivery_date: date,
) -> pd.Series:
    if context.smard_counterpart is None:
        raise RuntimeError(
            f"Challenge {context.challenge_id} ({context.target_code}/{context.area}) "
            "does not expose a confirmed SMARD counterpart. "
            "Use --data_source entsoe if you want to build a baseline anyway."
        )

    tz_name = context.reference_timezone or DEFAULT_TIMEZONE
    tz = ZoneInfo(tz_name)
    start_dt = datetime(delivery_date.year, delivery_date.month, delivery_date.day, tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)
    spec = context.smard_counterpart

    payload = {
        "request_form": [
            {
                "format": "CSV",
                "moduleIds": [spec.module_id],
                "region": spec.region,
                "timestamp_from": int(start_dt.timestamp() * 1000),
                "timestamp_to": int(end_dt.timestamp() * 1000),
                "type": "discrete",
                "language": "en",
                "resolution": spec.resolution,
            }
        ]
    }

    try:
        response = requests.post(SMARD_DOWNLOAD_URL, json=payload, timeout=45)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"SMARD request failed for {context.challenge_id}/{context.area}: {exc}"
        ) from exc

    points = _parse_smard_csv_points(
        response.content,
        timezone_name=tz_name,
        value_multiplier=spec.value_multiplier,
    )
    if not points:
        return pd.Series(dtype=float)

    index = pd.to_datetime([item["ts"] for item in points], utc=True)
    values = [float(item["value"]) for item in points]
    return pd.Series(values, index=index).sort_index()


def _fetch_source_series(
    *,
    data_source: str,
    context: ChallengeContext,
    delivery_date: date,
    entsoe_api_key: str,
) -> pd.Series:
    if data_source == "smard":
        return fetch_smard_series(context=context, delivery_date=delivery_date)
    if data_source == "entsoe":
        return fetch_entsoe_series(
            api_key=entsoe_api_key,
            context=context,
            delivery_date=delivery_date,
        )
    raise RuntimeError(f"Unsupported data source: {data_source}")


def _series_to_shifted_points(
    series: pd.Series,
    *,
    lookback_days: int,
    tz_name: str,
) -> List[Dict[str, float | str]]:
    tz = ZoneInfo(tz_name)
    points: List[Dict[str, float | str]] = []

    for ts, value in series.items():
        if hasattr(ts, "to_pydatetime"):
            ts_dt = ts.to_pydatetime()
        else:
            ts_dt = datetime.fromisoformat(str(ts))
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        shifted_local = ts_dt.astimezone(tz) + timedelta(days=lookback_days)
        points.append({"ts": shifted_local.isoformat(), "value": float(value)})

    points.sort(key=lambda item: str(item["ts"]))
    return points


def collect_probabilistic_history_samples(
    *,
    target_date: date,
    context: ChallengeContext,
    data_source: str,
    entsoe_api_key: str,
) -> Dict[str, List[float]]:
    if context.target_code not in TARGET_BASELINES:
        raise RuntimeError(
            f"Target '{context.target_code}' is not supported by the built-in baseline."
        )

    target_cfg = TARGET_BASELINES[context.target_code]
    history_by_ts: Dict[str, List[float]] = {}

    start_lookback_days = int(target_cfg["history_start_lookback_days"])
    step_days = int(target_cfg["history_step_days"])
    history_count = int(target_cfg["history_count"])
    tz_name = context.reference_timezone or DEFAULT_TIMEZONE

    for i in range(history_count):
        lookback_days = start_lookback_days + i * step_days
        delivery_date = target_date - timedelta(days=lookback_days)
        series = _fetch_source_series(
            data_source=data_source,
            context=context,
            delivery_date=delivery_date,
            entsoe_api_key=entsoe_api_key,
        )
        if series.empty:
            continue

        for point in _series_to_shifted_points(
            series,
            lookback_days=lookback_days,
            tz_name=tz_name,
        ):
            ts = str(point["ts"])
            history_by_ts.setdefault(ts, []).append(float(point["value"]))

    return history_by_ts


def _attach_objective_values(
    *,
    base_points: List[Dict[str, float | str]],
    context: ChallengeContext,
    history_by_ts: Dict[str, List[float]] | None = None,
) -> List[Dict[str, float | str | List[float]]]:
    objective = context.forecast_objective
    if objective == "point":
        return base_points

    history_lookup = history_by_ts or {}
    out: List[Dict[str, float | str | List[float]]] = []

    for point in base_points:
        ts = str(point["ts"])
        pf = float(point["value"])
        history_values = [float(v) for v in history_lookup.get(ts, [])]

        if objective == "quantile":
            if context.probabilistic_quantiles and history_values:
                values = np.quantile(
                    np.array(history_values, dtype=float),
                    context.probabilistic_quantiles,
                ).tolist()
            else:
                values = [pf for _ in context.probabilistic_quantiles]
            out.append({"ts": ts, "value": [float(v) for v in values]})
            continue

        if objective == "ensemble":
            ensemble_size = context.max_ensemble_size
            if history_values:
                values = history_values[:ensemble_size]
                if len(values) < ensemble_size:
                    pad_value = values[-1] if values else pf
                    values.extend([float(pad_value)] * (ensemble_size - len(values)))
            else:
                values = [pf for _ in range(ensemble_size)]
            out.append({"ts": ts, "value": [float(v) for v in values]})
            continue

        out.append({"ts": ts, "value": pf})

    return out


def build_payload_from_source(
    *,
    target_date: date,
    context: ChallengeContext,
    data_source: str,
    entsoe_api_key: str,
) -> dict:
    if not context.baseline_supported:
        raise RuntimeError(
            f"Target '{context.target_code}' is not supported by the built-in baseline. "
            "Provide your own custom_model.py override."
        )

    target_cfg = TARGET_BASELINES[context.target_code]
    lookback_days = int(target_cfg["point_lookback_days"])
    delivery_date = target_date - timedelta(days=lookback_days)
    tz_name = context.reference_timezone or DEFAULT_TIMEZONE

    series = _fetch_source_series(
        data_source=data_source,
        context=context,
        delivery_date=delivery_date,
        entsoe_api_key=entsoe_api_key,
    )
    if series.empty:
        source_label = "SMARD" if data_source == "smard" else "ENTSO-E"
        raise RuntimeError(
            f"No {source_label} data for {context.target_code}/{context.area} "
            f"on {delivery_date} (d-{lookback_days}). Data may not be published yet."
        )

    points = _series_to_shifted_points(
        series,
        lookback_days=lookback_days,
        tz_name=tz_name,
    )

    history_by_ts: Dict[str, List[float]] | None = None
    if context.forecast_objective in {"quantile", "ensemble"}:
        history_by_ts = collect_probabilistic_history_samples(
            target_date=target_date,
            context=context,
            data_source=data_source,
            entsoe_api_key=entsoe_api_key,
        )

    payload_points = _attach_objective_values(
        base_points=points,
        context=context,
        history_by_ts=history_by_ts,
    )

    payload_values = [point["value"] for point in payload_points]
    payload: dict[str, Any] = {"challenge_id": context.challenge_id, "values": payload_values}

    if len(context.areas) != 1:
        payload["area"] = context.area

    if context.target_period_type.lower() == "calendar_day":
        payload["target_date"] = target_date.isoformat()
    else:
        tz = ZoneInfo(context.target_period_timezone or tz_name)
        target_start = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            0,
            0,
            0,
            tzinfo=tz,
        )
        payload["target_start"] = target_start.isoformat()

    return payload


def build_payload(
    *,
    target_date: date,
    challenge_id: str,
    area: str | None,
    entsoe_api_key: str,
    api_base: str = DEFAULT_API_BASE,
    data_source: str = "smard",
    arena_api_key: str | None = None,
    challenge_context: ChallengeContext | None = None,
) -> dict:
    data_source = _normalized_data_source(data_source)
    context = challenge_context or _resolve_challenge_context(
        api_base=api_base,
        challenge_id=challenge_id,
        area=area,
        arena_api_key=arena_api_key,
    )

    custom_model = _load_custom_model_module()
    custom_build_payload = (
        getattr(custom_model, "build_payload", None) if custom_model else None
    )
    hook_kwargs = {
        "target_date": target_date,
        "challenge_id": context.challenge_id,
        "area": context.area,
        "entsoe_api_key": entsoe_api_key,
        "api_base": api_base,
        "data_source": data_source,
        "challenge_context": context,
        "challenge_detail": context.challenge_detail,
        "forecast_objective": context.forecast_objective,
        "tz_name": context.reference_timezone or DEFAULT_TIMEZONE,
    }

    if callable(custom_build_payload):
        custom_payload = _call_hook(custom_build_payload, **hook_kwargs)
        return _validate_payload(custom_payload, source="custom_model.build_payload")

    payload = build_payload_from_source(
        target_date=target_date,
        context=context,
        data_source=data_source,
        entsoe_api_key=entsoe_api_key,
    )

    custom_transform_payload = (
        getattr(custom_model, "transform_payload", None) if custom_model else None
    )
    if callable(custom_transform_payload):
        transformed_payload = _call_hook(
            custom_transform_payload,
            payload=payload,
            **hook_kwargs,
        )
        return _validate_payload(
            transformed_payload,
            source="custom_model.transform_payload",
        )

    return payload


def submit(
    payload: dict,
    api_key: str,
    api_base: str,
    dry_run: bool = False,
    verbose: bool = True,
    print_payload_on_dry_run: bool = True,
) -> bool:
    if dry_run:
        if verbose and print_payload_on_dry_run:
            print("Payload (dry run):")
            print(json.dumps(payload, indent=2))
        elif verbose:
            print("Dry run: payload not submitted.")
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

    transient_status_codes = {429, 502, 503, 504}
    retry_delays = [5, 15, 30]
    url = f"{api_base.rstrip('/')}/api/v1/submissions"
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    last_message = ""
    for attempt, delay in enumerate([0] + retry_delays, start=1):
        if delay:
            if verbose:
                print(
                    f"  Retrying in {delay}s (attempt {attempt}/{1 + len(retry_delays)})..."
                )
            time.sleep(delay)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.ok:
                data = resp.json()
                if verbose:
                    print(f"OK -> submission_id={data.get('submission_id')}")
                    submission_ids = data.get("submission_ids") or []
                    if len(submission_ids) > 1:
                        print(f"Created submission_ids={submission_ids}")
                    legacy_warning = data.get("legacy_compat_warning")
                    if legacy_warning:
                        print(f"Legacy compatibility warning: {legacy_warning}")
                    elif data.get("legacy_compat_mode"):
                        print(
                            "Legacy compatibility warning: legacy bundled challenge ids "
                            "are only accepted temporarily and will stop working soon."
                        )
                return True

            detail = _extract_error_detail(resp)
            last_message = f"HTTP {resp.status_code}" + (
                f" - {detail}" if detail else ""
            )
            if resp.status_code not in transient_status_codes:
                break
            if verbose:
                print(f"  Transient error: {last_message}", file=sys.stderr)
        except requests.RequestException as exc:
            last_message = str(exc)
            if verbose:
                print(f"  Connection error: {last_message}", file=sys.stderr)

    if verbose:
        print(f"Submit failed: {last_message}", file=sys.stderr)
    return False


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Submit one forecast to the Energy Arena."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        default=None,
        help="Target day in DD-MM-YYYY. Required unless --list_open_challenges or --check_setup is used.",
    )
    parser.add_argument(
        "--challenge_id",
        type=str,
        default="",
        help="Challenge id from python run_forecast_model.py --list_open_challenges.",
    )
    parser.add_argument(
        "--area",
        type=str,
        default="",
        help="Optional area override. Current challenges usually have exactly one area and do not need this.",
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
            or DEFAULT_API_BASE
        ).strip(),
        help="Arena API base URL.",
    )
    parser.add_argument(
        "--data_source",
        type=str,
        default=_get_default_data_source(local_env),
        choices=sorted(SUPPORTED_DATA_SOURCES),
        help="Baseline source for the built-in forecast generator (default: smard).",
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
        "--save_payload",
        type=str,
        default=None,
        help="Write the generated submission payload to a JSON text file.",
    )
    parser.add_argument(
        "--check_setup",
        action="store_true",
        help="Validate local keys, API reachability, and custom model loading, then exit.",
    )
    parser.add_argument(
        "--list_open_challenges",
        action="store_true",
        help="Fetch currently open challenges from the Energy Arena API and exit.",
    )
    parser.add_argument(
        "--include_quantiles",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--include_ensemble",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    data_source = _normalized_data_source(args.data_source)
    entsoe_key = local_env.get("ENTSOE_API_KEY", "").strip()
    arena_key = (args.api_key or "").strip()
    if args.use_global_env:
        entsoe_key = entsoe_key or os.environ.get("ENTSOE_API_KEY", "").strip()
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()

    if args.include_quantiles or args.include_ensemble:
        print(
            "Warning: --include_quantiles and --include_ensemble are ignored. "
            "The payload format is derived directly from the selected challenge.",
            file=sys.stderr,
        )

    if args.check_setup:
        sys.exit(
            run_setup_check(
                entsoe_key=entsoe_key,
                arena_key=arena_key,
                api_base=args.api_base,
                data_source=data_source,
            )
        )

    if args.list_open_challenges:
        try:
            challenge_infos = get_challenge_infos(
                args.api_base,
                arena_api_key=arena_key or None,
            )
        except Exception as exc:
            print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(1)
        print_open_challenge_infos(
            challenge_infos,
            api_base=args.api_base,
            arena_api_key=arena_key or None,
        )
        return

    if not arena_key and not args.dry_run:
        print(
            "Error: Arena API key required. Set ARENA_API_KEY in local .env, "
            "pass --api_key, or use --use_global_env. Run --check_setup for a quick diagnosis.",
            file=sys.stderr,
        )
        sys.exit(1)
    if data_source == "entsoe" and not entsoe_key:
        print(
            "Error: ENTSOE_API_KEY is required for --data_source entsoe. "
            "Switch to --data_source smard for the default keyless workflow.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.challenge_id:
        print(
            "Error: --challenge_id is required unless --list_open_challenges or --check_setup is used.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.target_date:
        print(
            "Error: --target_date is required unless --list_open_challenges or --check_setup is used.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        target_date = parse_target_date(args.target_date)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        context = _resolve_challenge_context(
            api_base=args.api_base,
            challenge_id=args.challenge_id,
            area=args.area or None,
            arena_api_key=arena_key or None,
        )
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    if data_source == "smard" and context.smard_counterpart is None:
        print(
            f"Error: challenge {context.challenge_id} does not currently expose a confirmed "
            "SMARD counterpart. Use --data_source entsoe if you want to build the baseline "
            "via ENTSO-E instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Target date: {target_date} | challenge: {context.challenge_id} | "
        f"target: {context.target_name} | area: {context.area} | "
        f"format: {context.accepted_forecast_format} | source: {data_source}"
    )

    try:
        active_lookup = get_active_challenge_lookup(
            args.api_base,
            arena_api_key=arena_key or None,
        )
    except Exception as exc:
        print(
            f"Warning: failed to fetch open challenge metadata: {exc}",
            file=sys.stderr,
        )
    else:
        current_info = active_lookup.get(context.challenge_id)
        if current_info is None:
            print(
                f"Warning: challenge '{context.challenge_id}' is not currently listed by /api/v1/challenges/open.",
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
        payload = build_payload(
            target_date=target_date,
            challenge_id=context.challenge_id,
            area=context.area,
            entsoe_api_key=entsoe_key,
            api_base=args.api_base,
            data_source=data_source,
            arena_api_key=arena_key or None,
            challenge_context=context,
        )
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if not str(exc).strip():
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    if args.save_payload:
        try:
            saved_path = save_payload_to_file(payload, args.save_payload)
        except Exception as exc:
            print(f"Error: failed to save payload: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Saved payload to {saved_path}")

    ok = submit(
        payload=payload,
        api_key=arena_key,
        api_base=args.api_base,
        dry_run=args.dry_run,
        verbose=True,
        print_payload_on_dry_run=not bool(args.save_payload),
    )
    if not ok and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
