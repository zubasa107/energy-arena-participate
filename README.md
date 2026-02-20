# Energy Arena — Participate with one script

Submit a day-ahead forecast to the Energy Arena by running **one Python script locally**. Uses ENTSO-E data: **d-1** for price, **d-2** for load and solar (same logic as BAREF’s `submit_d1_forecast`).

## What you need

- **Python 3.10+** (for `zoneinfo`)
- **ENTSOE_API_KEY** — [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) API key (required for fetches)
- **Arena API key** (register on the Arena and create an API key)
- **Arena base URL** (default: `https://api.energy-arena.org` — override with env or `--api_base` for local/testing)

## Quick start

### 1. Clone or download this repo

```bash
git clone <this-repo-url> energy-arena-participate
cd energy-arena-participate
```

### 2. Install dependency

```bash
pip install -r requirements.txt
```

### 3. Set API keys and base URL

**Option A — environment variables**

```bash
# Linux/macOS
export ENTSOE_API_KEY=your_entsoe_api_key_here
export ARENA_API_KEY=your_arena_api_key_here
export ARENA_API_BASE_URL=https://api.energy-arena.org

# Windows (PowerShell)
$env:ENTSOE_API_KEY = "your_entsoe_api_key_here"
$env:ARENA_API_KEY = "your_arena_api_key_here"
$env:ARENA_API_BASE_URL = "https://api.energy-arena.org"
```

**Option B — .env file (optional)**

Copy `.env.example` to `.env`, fill in `ENTSOE_API_KEY`, `ARENA_API_KEY`, and `ARENA_API_BASE_URL`, then load with `python-dotenv` or source it if your shell supports it. The script reads `os.environ`.

**Option C — command line**

Pass `--api_key` and `--api_base` to the script (see below).

### 4. Run the script

Submit a forecast for a specific day:

```bash
python submit_forecast.py --target_date 20-02-2026 --challenge_id day_ahead_price --area DE_LU
```

- **target_date**: Day you are forecasting, in `DD-MM-YYYY`.
- **challenge_id**: `day_ahead_price` | `day_ahead_load` | `day_ahead_solar` (default: `day_ahead_price`).
- **area**: `DE_LU` | `AT` (default: `DE_LU`).

With API key on the command line:

```bash
python submit_forecast.py --target_date 20-02-2026 --challenge_id day_ahead_price --area DE_LU --api_key YOUR_KEY --api_base https://api.energy-arena.org
```

Dry run (print payload, do not submit):

```bash
python submit_forecast.py --target_date 20-02-2026 --dry_run
```

### 5. Daily run at 11:30 CET (all 3 challenges × 2 areas)

To submit for **all** challenges and areas in one go (target = tomorrow), use the daily runner:

```bash
python run_daily_submissions.py
```

- Uses **tomorrow** (Europe/Berlin) as target date, so at 11:30 CET you are before the 12:00 deadline.
- Optional: `--target_date DD-MM-YYYY` to override; `--dry_run` to test without submitting.

**Executables for scheduling:**

- **Windows:** `run_daily_submissions.bat` or `run_daily_submissions.ps1`
- **Linux/macOS:** run `run_daily_submissions.py` from cron

- **Windows (detailed):** **[WINDOWS_TASK_SCHEDULER.md](WINDOWS_TASK_SCHEDULER.md)** — step-by-step Task Scheduler setup for 11:30 CET.  
- **All platforms:** [SCHEDULE.md](SCHEDULE.md) — short reference for Task Scheduler and cron.

## What the script does

1. **Fetches ENTSO-E data** for the relevant lookback day:
   - **day_ahead_price**: d-1 day-ahead prices → shift to target date.
   - **day_ahead_load**: d-2 actual load → shift to target date.
   - **day_ahead_solar**: d-2 actual solar generation → shift to target date.
2. Builds the submission payload (timestamps in `Europe/Berlin`, number of points matches ENTSO-E resolution).
3. POSTs to `{ARENA_API_BASE_URL}/api/v1/submissions` with header `X-API-Key`.

This matches the forecasting logic in BAREF’s `submit_d1_forecast.py` (with d-2 for load and solar).

## Submission rules (Arena)

- **Target day**: Use the calendar day you are forecasting in `DD-MM-YYYY`.
- **Deadline**: The Arena enforces a gate closure; submit before the challenge deadline for that target day.
- **Multiple submissions**: You can usually overwrite your forecast for the same target by submitting again (latest-before-deadline is used).

## Getting an API key

1. Open the Arena (the URL provided by the operator).
2. Register / log in.
3. Go to your profile or API keys section.
4. Create an API key and copy it into `ARENA_API_KEY` or `--api_key`.

## Repository layout

- `submit_forecast.py` — single submission: one challenge, one area.
- `run_daily_submissions.py` — submit all 3 challenges × 2 areas (target = tomorrow).
- `run_daily_submissions.bat` / `run_daily_submissions.ps1` — run the daily script (for scheduling).
- `SCHEDULE.md` — how to schedule at 11:30 CET (Task Scheduler, cron).
- `requirements.txt` — `requests`, `pandas`, `entsoe-py`, `tzdata`.
- `.env.example` — template for `ENTSOE_API_KEY`, `ARENA_API_KEY`, and `ARENA_API_BASE_URL`.
- `README.md` — this file.

Standalone: no dependency on the BAREF codebase; run one script locally to participate.
