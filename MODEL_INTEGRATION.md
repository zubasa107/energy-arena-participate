# Integrate Your Own Model

This starter repository is intentionally split into three parts:

1. challenge and schedule discovery
2. payload generation
3. payload submission

If you want to use your own model, change only the payload-generation part and leave the API interaction intact.

## Recommended integration point

The recommended path is:

1. copy `custom_model_template.py` to `custom_model.py`
2. edit `transform_payload(...)` inside `custom_model.py`

Both `submit_forecast.py` and `run_daily_submissions.py` automatically load
`custom_model.py` if it exists, so you do not need to edit the starter scripts
directly.

Internally, both scripts still go through the same shared payload hook:

- `submit_forecast.py` -> `build_payload(...)`
- `run_daily_submissions.py` -> `build_payload(...)`

## Recommended procedure

1. Run the baseline once unchanged.
   Confirm that `python submit_forecast.py ...` works end-to-end before changing anything.
2. Keep the challenge lookup and submission flow.
   Leave `--list_open_challenges`, `submit(...)`, API keys, and retry handling unchanged.
3. Copy `custom_model_template.py` to `custom_model.py`.
4. Edit `transform_payload(...)` with your own model logic.
5. Keep the payload contract unchanged.
   Your model can change the forecast values, but not the expected JSON structure.
6. Validate with a dry run first.
   Use `--dry_run --save_payload your_payload.txt` before sending real submissions.
7. After one manual run works, daily automation uses the same builder automatically.

Copy command examples:

```bash
# Windows PowerShell
Copy-Item custom_model_template.py custom_model.py

# macOS / Linux
cp custom_model_template.py custom_model.py
```

## Payload contract you must keep

The submission payload must still look like this:

```json
{
  "challenge_id": "day_ahead_price",
  "area": "DE_LU",
  "target_start": "2026-03-24T00:00:00+01:00",
  "points": [
    {
      "ts": "2026-03-24T00:00:00+01:00",
      "value": 0.0
    }
  ]
}
```

Rules:

- Keep the top-level keys: `challenge_id`, `area`, `target_start`, `points`
- Keep `points` sorted by timestamp
- For point forecasts, `value` is a single number
- For probabilistic forecasts, `value` is a vector in the exact order:
  `[pf, quantiles..., ensembles...]`
- Use `python submit_forecast.py --list_open_challenges` to inspect the accepted forecast format for each challenge

## Easiest integration pattern

The safest way is to reuse the baseline payload as a timestamp template and replace only the values.

```python
def transform_payload(
    payload,
    *,
    target_date,
    challenge_id,
    area,
    entsoe_api_key,
    api_base,
    include_quantiles,
    include_ensemble,
    tz_name,
):
    predictions = my_model_predict(...)

    for point, prediction in zip(payload["points"], predictions, strict=True):
        point["value"] = float(prediction)

    return payload
```

Why this pattern is useful:

- the timestamps are already correct
- `challenge_id`, `area`, and `target_start` are already in place
- you only replace the forecast values
- the same file is used by both manual submissions and daily automation

## If your model outputs quantiles or ensembles

If your model already predicts probabilistic outputs, write the vectors directly into `point["value"]`.

Example:

```python
point["value"] = [
    pf,
    q2_5,
    q25,
    q50,
    q75,
    q97_5,
    e1,
    e2,
    e3,
]
```

Important:

- `pf` must stay first
- quantiles must come next in the configured order
- ensemble members must come last

You can also use the baseline payload itself as a shape template. If
`--include_quantiles` or `--include_ensemble` is active, the incoming
`payload["points"][i]["value"]` already has the correct vector structure.

## If your model needs extra packages or files

- add extra Python packages to `requirements.txt`
- load your trained model weights from a stable local path
- keep secrets in `.env`, not in code

## Validation checklist

Before sending real submissions:

1. Run `python submit_forecast.py --list_open_challenges`
2. Run your model path with `--dry_run --save_payload test_payload.txt`
3. Open the saved payload and inspect timestamps and value shapes
4. Submit one manual forecast
5. Only then switch on daily automation

## Automation note

`run_daily_submissions.py` imports `build_payload(...)` from `submit_forecast.py`.

That shared builder automatically loads `custom_model.py` too, so once your
manual run works, the daily automation path uses the same custom model
automatically.

## Advanced option: full override

If you do not want to start from the baseline payload at all, `custom_model.py`
may define `build_payload(...)` instead of `transform_payload(...)`.

That gives you full control, but then you must build the entire payload
yourself, including timestamps and value ordering.
