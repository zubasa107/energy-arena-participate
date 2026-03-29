# Model Integration

The starter repository is split into three parts:

1. challenge discovery
2. payload generation
3. payload submission

If you want to use your own model, change only the payload generation step and
leave challenge lookup plus submission flow untouched.

## Recommended integration point

Recommended path:

1. copy `custom_model_template.py` to `custom_model.py`
2. edit `transform_payload(...)`

Both `naiv_model.py` and `run_daily_submissions.py` automatically load
`custom_model.py` if it exists. `submit_payload.py` only sends the saved payload
and does not modify it.

Internally both scripts go through the same shared hook:

- `naiv_model.py` -> `build_payload(...)`
- `run_daily_submissions.py` -> `build_payload(...)`

## Recommended procedure

1. Run the baseline once unchanged.
2. Confirm one successful local payload generation and one successful real submission.
3. Copy `custom_model_template.py` to `custom_model.py`.
4. Edit `transform_payload(...)` with your own model logic.
5. Keep the payload contract unchanged.
6. Validate by generating and inspecting a saved payload before sending real submissions.
7. After one manual run works, daily automation uses the same hook automatically.

Copy examples:

```bash
# Windows PowerShell
Copy-Item custom_model_template.py custom_model.py

# macOS / Linux
cp custom_model_template.py custom_model.py
```

## Payload contract

The safest pattern is to keep the incoming payload structure and replace only
the values in `payload["values"]`.

Current payload rules:

- keep top-level `challenge_id`
- keep `values` in the original order
- keep `target_date` for current calendar-day challenges
- `area` is optional and usually omitted for current single-area challenges
- `target_start` is only needed for non-`calendar_day` challenges
- for point challenges, each entry in `values` is a scalar
- for quantile challenges, each entry in `values` is exactly the configured quantile list
- for ensemble challenges, each entry in `values` is exactly the configured ensemble-member list

## Easiest integration pattern

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

Why this is the safest pattern:

- target-period anchoring is already correct
- the correct challenge format is already resolved
- you only replace the forecast values
- the same hook is used by manual submissions and automation

## Practical notes

- `data_source` tells you whether the built-in baseline came from `smard` or `entsoe`
- `challenge_context` contains resolved challenge metadata like target code, area, objective, quantiles, and SMARD counterpart info
- `challenge_detail` is the raw API response for the selected challenge

## Full override

If you do not want to start from the built-in baseline at all, define
`build_payload(...)` in `custom_model.py` instead of `transform_payload(...)`.

That gives you full control, but then you must build the full payload yourself
and still respect the challenge-specific format.

## Validation checklist

Before sending real submissions:

1. Run `python naiv_model.py --list_open_challenges`
2. Run `python naiv_model.py --target_date DD-MM-YYYY --challenge_id X --save_payload test_payload.txt`
3. Open the saved payload and inspect the target day plus value shapes
4. Run `python submit_payload.py --payload_path test_payload.txt`
5. Only then switch on daily automation
