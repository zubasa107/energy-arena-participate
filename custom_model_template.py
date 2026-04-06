"""
Copy this file to custom_model.py and edit transform_payload(...).

run_forecast_model.py and run_daily_submissions.py automatically load
custom_model.py if it exists in the repository root.

The incoming payload already has:
- the correct challenge_id
- the correct canonical target_start anchor for the chosen challenge
- the correct value shape for point / quantile / ensemble mode

The safest way to integrate your own model is to replace only the forecast
values and return the payload.

If you want to reuse the repository's source-data logic, you can import helper
functions from data_loaders.py inside custom_model.py.
"""

from __future__ import annotations

from datetime import date, datetime


def transform_payload(
    payload: dict,
    *,
    target_date: date,
    target_start: datetime,
    challenge_id: str,
    area: str,
    entsoe_api_key: str,
    api_base: str,
    data_source: str,
    challenge_context,
    challenge_detail: dict,
    forecast_objective: str,
    tz_name: str,
) -> dict:
    """
    Edit this function with your own model logic.

    Working default:
    - returns the baseline payload unchanged

    Typical customization:
    - compute your own forecast values
    - write those values into payload["values"][i]
    - keep the payload structure unchanged
    """
    del (
        target_date,
        target_start,
        challenge_id,
        area,
        entsoe_api_key,
        api_base,
        data_source,
        challenge_context,
        challenge_detail,
        forecast_objective,
        tz_name,
    )

    for index, original_value in enumerate(payload["values"]):

        # Replace this section with your own model output.
        # The current code is intentionally a no-op scaffold that preserves
        # the baseline payload shape.
        if isinstance(original_value, list):
            payload["values"][index] = [float(v) for v in original_value]
        else:
            payload["values"][index] = float(original_value)

    return payload
