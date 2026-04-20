# Energy Arena Participate

This starter repository is intentionally small.

As a participant, you only need these scripts:

- `run_forecast_model.py`
- `submit_forecast_to_energy_arena.py`
- `run_daily_submissions.py`

If you want to use the repository as a basis for your own model, these helper
modules are also relevant:

- `data_loaders.py`
- `starter_model.py`

Everything else is internal support code or documentation.

## First submission

### 1. Install
Setting up the repository and virtual environment.
```bash
git clone <this-repo-url> energy-arena-participate
cd energy-arena-participate
python -m venv .venv
#ACtivating the virtual enviorment for Mac/Linux
source .venv/bin/activate

# activating it using Windows CMD
.venv\Scripts\activate.bat

# activating it using Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```
A virtual environment isolates project dependencies, preventing version conflicts between projects and keeping your global Python installation clean.
Activate it before every session (like above) and deactivate it like below after you are finished.
```bash
deactivate
```
### 2. Create `.env`

Copy `.env.example` to `.env` and fill in:

```env
ARENA_API_KEY=your_arena_api_key_here
ARENA_API_BASE_URL=https://api.energy-arena.org
BASELINE_DATA_SOURCE=smard

# Optional only if you want --data_source entsoe
# ENTSOE_API_KEY=your_entsoe_api_key_here
```

### 3. List the open challenges

```bash
python run_forecast_model.py --list_open_challenges
```

This prints:

- `Challenge ID`
- `Target`
- `Area`
- `Forecast Format`
- next submission deadline
- next target start

### 4. Generate one local forecast

```bash
python run_forecast_model.py --target_start 2026-03-27T00:00:00+01:00 --challenge_id 1 --save_payload test_payload.json
```

If you omit both `--target_start` and `--target_date`, the script uses the selected challenge's
`Next Target Start` from `--list_open_challenges` automatically:

```bash
python run_forecast_model.py --challenge_id 1 --save_payload test_payload.json
```

For current calendar-day challenges, `--target_date DD-MM-YYYY` is still accepted
as a convenience shortcut, but generated payloads are anchored by
`challenge_id + target_start`.

What this does:

- resolves the selected challenge
- uses the built-in starter model
- creates a local payload file
- does not submit anything yet

Current challenges are usually single-area, so you normally do not need `--area`.

If you explicitly want ENTSO-E instead of the default SMARD baseline:

```bash
python run_forecast_model.py --target_start 2026-03-27T00:00:00+01:00 --challenge_id 1 --data_source entsoe --save_payload test_payload.json
```

### 5. Submit the saved payload

```bash
python submit_forecast_to_energy_arena.py --payload_path test_payload.json
```

What this does:

- loads the saved payload
- validates it
- sends it to Energy Arena via API POST

Then check the dashboard for the submission status.

## What each script is for

### `run_forecast_model.py`

Use this for manual participation.

- list open challenges
- generate one local payload
- check local setup with `--check_setup`

### `submit_forecast_to_energy_arena.py`

Use this to send a saved payload.

### `run_daily_submissions.py`

Use this only after one manual submission already works.

It submits all currently open challenges automatically.

## Helper modules for your own model

### `data_loaders.py`

Provides reusable loader functions:

- `load_smard_series(...)`
- `load_entsoe_series(...)`
- `load_source_series(...)`

These are the functions students can import if they want to build their own
model on top of the same data sources.

### `starter_model.py`

Provides:

- `build_starter_payload(...)`

This is the built-in baseline model logic used by the starter flow.

## Integrate your own model

If you want to replace the built-in starter model:

1. Copy `custom_model_template.py` to `custom_model.py`
2. Edit `transform_payload(...)`
3. Generate one local payload again
4. Submit it manually once
5. Only then use daily automation

Detailed notes:

- `MODEL_INTEGRATION.md`

## Daily automation

```bash
python run_daily_submissions.py
```

Without `--target_start` or `--target_date`, each selected challenge uses its
own `next_target_start` from the open challenge API.

Each generated payload is also archived automatically under
`.\submitted_payloads\challenge_<id>\`.

Optional examples:

```bash
python run_daily_submissions.py --dry_run
python run_daily_submissions.py --target_start 2026-03-27T00:00:00+01:00
python run_daily_submissions.py --target_date 27-03-2026
python run_daily_submissions.py --challenge_id 1
python run_daily_submissions.py --data_source entsoe
python run_daily_submissions.py --use_global_env
```

## Scheduling

- Windows: `WINDOWS_TASK_SCHEDULER.md`
- Cross-platform notes: `SCHEDULE.md`

The recommended wrappers `run_daily_submissions.bat`,
`run_daily_submissions.ps1` and `run_daily_submissions.sh` now write logs to `.\logs\`, including a timestamped
file per run and `run_daily_submissions_latest.log`.
Daily automation also archives the generated payload JSON files in
`.\submitted_payloads\challenge_<id>\`.
