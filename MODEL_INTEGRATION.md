# Model Integration

The starter workflow has only two manual steps:

1. generate a local payload with `run_forecast_model.py`
2. submit it with `submit_forecast_to_energy_arena.py`

If you want to use your own model, change only the payload-generation step.

The repository now exposes two explicit helper modules for that:

- `data_loaders.py` for historical source-data loading
- `starter_model.py` for the built-in starter baseline

## Recommended integration point

1. Copy `custom_model_template.py` to `custom_model.py`
2. Edit `transform_payload(...)`

`run_forecast_model.py` and `run_daily_submissions.py` automatically load `custom_model.py` if it exists.

`submit_forecast_to_energy_arena.py` only sends the saved payload and does not modify it.

## Available building blocks

### `data_loaders.py`

Reusable loader functions:

- `load_smard_series(...)`
- `load_entsoe_series(...)`
- `load_source_series(...)`

These let students keep the same upstream data-loading logic while replacing
only the forecasting step.

### `starter_model.py`

Reusable starter baseline:

- `build_starter_payload(...)`

This is the current naive historical baseline used by the starter flow.

## Recommended procedure

1. Run the built-in baseline once unchanged.
2. Confirm one successful local payload generation.
3. Confirm one successful real submission.
4. Copy `custom_model_template.py` to `custom_model.py`.
5. Edit `transform_payload(...)`.
6. Keep the payload structure unchanged.
7. Validate by generating and inspecting a saved payload before sending real submissions.
8. Only then enable daily automation.

## Payload contract

The safest pattern is to keep the incoming payload structure and replace only the values in `payload["values"]`.

Current payload rules:

- keep top-level `challenge_id`
- keep `values` in the original order
- keep `target_date` for current calendar-day challenges
- `area` is optional and usually omitted for current single-area challenges
- `target_start` is only needed for non-`calendar_day` challenges
- for point challenges, each entry in `values` is a scalar
- for quantile challenges, each entry in `values` is exactly the configured quantile list
- for ensemble challenges, each entry in `values` is exactly the configured ensemble-member list

## Safest implementation pattern

```python
def transform_payload(
    payload,
    *,
    target_date,
    challenge_id,
    area,
    entsoe_api_key,
    api_base,
    data_source,
    challenge_context,
    challenge_detail,
    forecast_objective,
    tz_name,
):
    predictions = my_model_predict(...)

    for index, prediction in enumerate(predictions):
        if isinstance(payload["values"][index], list):
            payload["values"][index] = [float(v) for v in prediction]
        else:
            payload["values"][index] = float(prediction)

    return payload
```

Why this is safest:

- target-period anchoring is already correct
- the challenge format is already resolved
- you only replace the forecast values
- the same hook is used by manual submissions and automation

## Validation checklist

Before sending real submissions:

1. Run `python run_forecast_model.py --list_open_challenges`
2. Run `python run_forecast_model.py --target_date DD-MM-YYYY --challenge_id X --save_payload test_payload.json`
3. Open the saved payload and inspect it
4. Run `python submit_forecast_to_energy_arena.py --payload_path test_payload.json`
5. Only then switch on daily automation
