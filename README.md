# Energy Arena - Participate with one script

Submit day-ahead forecasts to the Energy Arena by running one Python script locally.

Point forecast logic:
- `day_ahead_price`: d-1 ENTSO-E day-ahead prices
- `day_ahead_load`: d-2 ENTSO-E actual load
- `day_ahead_solar`: d-2 ENTSO-E actual solar generation
- `day_ahead_wind`: d-2 ENTSO-E actual onshore wind generation

Optional probabilistic extension:
- `--include_quantiles`: append quantile forecasts estimated from historical analog values
- `--include_ensemble`: append quantile forecasts plus ensemble members estimated from the same historical analog values

The probabilistic history logic mirrors the current naive benchmark:
- price/load: weekly analogs (`d-7`, `d-14`, `d-21`, ...)
- solar/wind: daily submission-aware analogs (`d-2`, `d-3`, `d-4`, ...)

## What you need

- Python 3.10+
- `ENTSOE_API_KEY` (ENTSO-E Transparency Platform security token)
- `ARENA_API_KEY`
- Arena base URL (default: `https://api.energy-arena.org`)

## Quick start

### 1) Clone/download and install dependencies

```bash
git clone <this-repo-url> energy-arena-participate
cd energy-arena-participate
pip install -r requirements.txt
```

With conda (recommended to keep dependencies isolated):

```bash
conda create --name energyarena python=3.10
conda activate energyarena
pip install -r requirements.txt
```

### 2) Create local `.env` (recommended)

Copy `.env.example` to `.env` and set your keys:

```bash
cp .env.example .env
```

```env
ENTSOE_API_KEY=your_entsoe_api_key_here
ARENA_API_KEY=your_arena_api_key_here
ARENA_API_BASE_URL=https://api.energy-arena.org
```

Both scripts read `.env` automatically.

Optional: allow fallback to global environment variables with `--use_global_env`.

### 3) Inspect the currently open challenges

```bash
python submit_forecast.py --list_open_challenges
```

This calls the public `GET /api/v1/challenges/open` endpoint and prints:

- active `challenge_id` values
- valid `areas`
- `next_submission_deadline`
- `next_target_start`
- a `payload_example`

If you want the raw helper in your own Python code:

```python
import os

from challenge_catalog import get_challenge_infos

infos = get_challenge_infos(
    os.environ.get("ARENA_API_BASE_URL", "https://api.energy-arena.org"),
)
print(infos["active_challenges"])
```

### 4) Submit one point forecast

```bash
python submit_forecast.py --target_date 20-03-2026 --challenge_id day_ahead_price --area DE_LU
```

- `target_date`: `DD-MM-YYYY` — **must be tomorrow's date** (the day you are forecasting for).
  - Using a date **more than one day ahead** fails with `NoMatchingDataError` because the required ENTSO-E source data has not been published yet.
  - Using a **past date** fails with a "past submission deadline" error from the platform.
- `challenge_id`: `day_ahead_price` | `day_ahead_load` | `day_ahead_solar` | `day_ahead_wind`
- `area`: `DE_LU` | `AT`

**What the script actually does:** it fetches recent ENTSO-E data (e.g. yesterday's day-ahead prices for `day_ahead_price`) and shifts those values to tomorrow as a naive forecast. No custom model file is needed — the ENTSO-E historical data itself is the forecast. The JSON payload is then POSTed directly to `{ARENA_API_BASE_URL}/api/v1/submissions` using your `ARENA_API_KEY`.

**Troubleshooting:**
- `Submit failed: HTTP 503 - Service Unavailable` → transient server-side error (not related to your API key or login). Wait a moment and retry — the platform may be temporarily starting up or overloaded.
- `NoMatchingDataError` → use tomorrow's date (ENTSO-E data for that delivery period does not exist yet).
- `past submission deadline` → only tomorrow's date is accepted.

Optional overrides:

```bash
python submit_forecast.py --target_date 20-02-2026 --challenge_id day_ahead_price --area DE_LU --api_key YOUR_KEY --api_base https://api.energy-arena.org
```

Dry run:

```bash
python submit_forecast.py --target_date 20-02-2026 --dry_run
```

Example payload format:

- `example_payload.txt` contains an actual `--dry_run` point payload for `2026-03-20` with `96` quarter-hour timestamps (`00:00` to `23:45`, `Europe/Berlin`).
- `example_payload_probabilistic.txt` contains the matching actual `--dry_run --include_ensemble` payload for `2026-03-20`, with vector values ordered as `[point, q0.025, q0.25, q0.5, q0.75, q0.975, e1, ..., e10]`.

### 5) Submit quantiles or ensembles optionally

Quantiles:

```bash
python submit_forecast.py --target_date 20-02-2026 --challenge_id day_ahead_price --area DE_LU --include_quantiles
```

Quantiles plus ensemble members:

```bash
python submit_forecast.py --target_date 20-02-2026 --challenge_id day_ahead_price --area DE_LU --include_ensemble
```

Notes:
- `--include_ensemble` also includes quantiles, because the platform expects the vector order `[point, quantiles..., ensembles...]`
- quantile definitions and maximum ensemble size are pulled from the public challenge API when available, otherwise the local fallback mapping is used
- for a first test, keep the default point-forecast mode and switch on probabilistic output afterwards

### 6) Daily run at 11:30 CET (all 4 challenges x 2 areas)

```bash
python run_daily_submissions.py
```

Optional:

```bash
python run_daily_submissions.py --include_quantiles
python run_daily_submissions.py --include_ensemble
python run_daily_submissions.py --target_date 20-02-2026
python run_daily_submissions.py --dry_run
python run_daily_submissions.py --use_global_env
```

## Scheduling

- Windows (detailed): `WINDOWS_TASK_SCHEDULER.md`
- All platforms (short reference): `SCHEDULE.md`
- Launchers: `run_daily_submissions.bat`, `run_daily_submissions.ps1`

## What the scripts do

1. Fetch ENTSO-E data for the chosen challenge and area
2. Shift timestamps to the target date (`Europe/Berlin`)
3. Optionally estimate quantiles and ensemble members from historical analog values
4. POST to `{ARENA_API_BASE_URL}/api/v1/submissions` with header `X-API-Key`

## Repository layout

- `submit_forecast.py` - single submission
- `challenge_catalog.py` - helper for `GET /api/v1/challenges/open`
- `run_daily_submissions.py` - daily batch submission
- `run_daily_submissions.bat` / `run_daily_submissions.ps1` - scheduler-friendly launchers
- `SCHEDULE.md` - scheduling reference (Windows + cron)
- `WINDOWS_TASK_SCHEDULER.md` - step-by-step Windows setup
- `example_payload.txt` - one example submission payload (JSON in `.txt`)
- `example_payload_probabilistic.txt` - one example payload with point + quantiles + ensembles (JSON in `.txt`)
- `.env.example` - local config template
- `requirements.txt` - dependencies
