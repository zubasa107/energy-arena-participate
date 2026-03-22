"""
Copy this file to custom_model.py and edit transform_payload(...).

submit_forecast.py and run_daily_submissions.py automatically load
custom_model.py if it exists in the repository root.

The incoming payload already has:
- the correct challenge_id, area, and target_start
- the correct target timestamps for the chosen day
- the correct value shape for point / quantile / ensemble mode

The safest way to integrate your own model is to replace only the forecast
values and return the payload.
"""

from __future__ import annotations

from datetime import date


def transform_payload(
    payload: dict,
    *,
    target_date: date,
    challenge_id: str,
    area: str,
    entsoe_api_key: str,
    api_base: str,
    include_quantiles: bool,
    include_ensemble: bool,
    tz_name: str,
) -> dict:
    """
    Edit this function with your own model logic.

    Working default:
    - returns the baseline payload unchanged

    Typical customization:
    - compute your own forecast values
    - write those values into payload["points"][i]["value"]
    - keep the payload structure unchanged
    """
    del target_date, challenge_id, area, entsoe_api_key, api_base, tz_name

    for point in payload["points"]:
        original_value = point["value"]

        # Replace this section with your own model output.
        # The current code is intentionally a no-op scaffold that preserves
        # the baseline payload shape.
        if isinstance(original_value, list):
            point_forecast = float(original_value[0])
            quantile_and_ensemble_values = [float(v) for v in original_value[1:]]

            if include_ensemble:
                point["value"] = [point_forecast, *quantile_and_ensemble_values]
            elif include_quantiles:
                point["value"] = [point_forecast, *quantile_and_ensemble_values]
            else:
                point["value"] = point_forecast
        else:
            point["value"] = float(original_value)

    return payload
