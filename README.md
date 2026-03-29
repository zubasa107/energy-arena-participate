# Energy Arena Participate

Generate a local forecast payload first and then submit it to Energy Arena.

The built-in baseline is now **SMARD-first**:

- default: `smard` baseline, no extra data key required
- optional: `entsoe` baseline, requires `ENTSOE_API_KEY`

The starter flow is now split into two manual steps:

- `naiv_model.py` resolves the selected challenge and generates a local payload
- `submit_payload.py` submits that saved payload to Energy Arena via API POST

The payload format is still derived automatically from the selected challenge,
so point, quantile, and ensemble challenges use the correct shape.

## What you need for a first submission

- Python 3.10+
- `ARENA_API_KEY`
- optional `ENTSOE_API_KEY` only if you explicitly want `--data_source entsoe`

## Student path

Use this flow for the shortest route to a first successful submission:

1. Copy `.env.example` to `.env`
2. Fill `ARENA_API_KEY`
3. Run `python naiv_model.py --list_open_challenges`
4. Generate one local payload
5. Inspect the saved payload
6. Submit the payload to Energy Arena

Minimal commands:

```bash
python naiv_model.py --list_open_challenges
python naiv_model.py --target_date 27-03-2026 --challenge_id 1 --save_payload test_payload.txt
python submit_payload.py --payload_path test_payload.txt
```

## Quick start

### 1) Clone/download and install dependencies

```bash
git clone <this-repo-url> energy-arena-participate
cd energy-arena-participate
pip install -r requirements.txt
```

Optional conda environment:

```bash
conda create --name energyarena python=3.10
conda activate energyarena
pip install -r requirements.txt
```

### 2) Create local `.env`

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Example:

```env
ARENA_API_KEY=your_arena_api_key_here
ARENA_API_BASE_URL=https://api.energy-arena.org
BASELINE_DATA_SOURCE=smard

# Optional only for --data_source entsoe
# ENTSOE_API_KEY=your_entsoe_api_key_here
```

Both scripts read `.env` automatically.

### 3) Optional: check your setup

```bash
python naiv_model.py --check_setup
```

This verifies:

- whether `.env` exists
- whether `ARENA_API_KEY` is available
- whether the open challenge catalog can be reached
- whether a local `custom_model.py` is picked up successfully
- whether your chosen default baseline source is usable

### 4) Inspect open challenges

```bash
python naiv_model.py --list_open_challenges
```

The table shows:

- `challenge_id`
- target / challenge name
- area
- accepted forecast format
- baseline source (`smard` or `entsoe`)
- next submission deadline
- next target start

Use one of the printed `challenge_id` values in the next step.

### 5) Generate one local forecast payload

```bash
python naiv_model.py --target_date 27-03-2026 --challenge_id 1 --save_payload test_payload.txt
```

Notes:

- `target_date` must be tomorrow's date for day-ahead challenges
- the script resolves the challenge format automatically
- the preferred payload is compact: `challenge_id + target_date + values`
- for current single-area challenges, you normally do **not** need `--area`
- the built-in naive baseline uses `smard` by default
- the command saves the generated payload locally and does not submit yet

Optional ENTSO-E mode:

```bash
python naiv_model.py --target_date 27-03-2026 --challenge_id 1 --data_source entsoe --save_payload test_payload.txt
```

Use this only if:

- the selected challenge does not expose a confirmed SMARD counterpart, or
- you explicitly want to build the baseline from ENTSO-E data

### 6) Submit the saved payload

```bash
python submit_payload.py --payload_path test_payload.txt
```

Notes:

- this sends the saved JSON payload to Energy Arena via API POST
- the payload is stored first and then evaluated later once realized target data is available
- after submitting, check the dashboard for the new entry and its current status

## Current built-in baseline behavior

Point baseline:

- day-ahead price: previous day price values (`d-1`)
- total load: previous actual load values with the current lookback pattern
- solar generation: previous actual solar values
- wind generation: previous actual wind values

Probabilistic baseline:

- quantile challenges: quantiles are estimated from historical analog values
- ensemble challenges: ensemble members are drawn from historical analog values
- price/load use weekly analog history
- solar/wind use daily submission-aware analog history

The script reads the required quantiles or ensemble size directly from the live
challenge detail endpoint.

## Integrate your own model

If you want to replace the built-in baseline with your own model:

1. Copy `custom_model_template.py` to `custom_model.py`
2. Edit `transform_payload(...)`
3. Validate by generating one local payload
4. Submit one manual forecast
5. Only then enable daily automation

Copy commands:

```bash
# Windows PowerShell
Copy-Item custom_model_template.py custom_model.py

# macOS / Linux
cp custom_model_template.py custom_model.py
```

Detailed guide:

- `MODEL_INTEGRATION.md`

## Daily automation

Run all currently open challenges:

```bash
python run_daily_submissions.py
```

Optional:

```bash
python run_daily_submissions.py --dry_run
python run_daily_submissions.py --target_date 27-03-2026
python run_daily_submissions.py --challenge_id 1
python run_daily_submissions.py --data_source entsoe
python run_daily_submissions.py --use_global_env
```

The batch runner now fetches the open challenge list from the API and processes
those challenge ids directly instead of relying on a hardcoded local list.

## Scheduling

- Windows: `WINDOWS_TASK_SCHEDULER.md`
- Cross-platform notes: `SCHEDULE.md`
- Launchers: `run_daily_submissions.bat`, `run_daily_submissions.ps1`

## Repository layout

- `naiv_model.py` - generate one local payload with the starter model
- `submit_payload.py` - submit a saved payload via API POST
- `submit_forecast.py` - legacy combined helper for build-and-submit in one command
- `run_daily_submissions.py` - batch submission for open challenges
- `challenge_catalog.py` - challenge discovery helpers
- `custom_model_template.py` - starter hook for your own model
- `MODEL_INTEGRATION.md` - custom model guide
- `SCHEDULE.md` - scheduling reference
- `WINDOWS_TASK_SCHEDULER.md` - Windows Task Scheduler setup
- `.env.example` - local config template
- `requirements.txt` - dependencies
