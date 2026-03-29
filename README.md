# Energy Arena Participate

Generate one local forecast, inspect the payload, and then submit it to Energy Arena.

The repository is now organized around five user-facing scripts:

- `load_smard_data.py` - download the SMARD source data used by the starter model
- `load_entsoe_data.py` - download the ENTSO-E source data used by the starter model
- `run_forecast_model.py` - generate one local forecast payload
- `submit_forecast_to_energy_arena.py` - submit a saved payload via API POST
- `master.py` - run generation and submission in one command

Older names are still available as compatibility aliases:

- `naiv_model.py` -> `run_forecast_model.py`
- `submit_payload.py` -> `submit_forecast_to_energy_arena.py`
- `submit_forecast.py` -> legacy combined helper

## What you need for a first submission

- Python 3.10+
- `ARENA_API_KEY`
- optional `ENTSOE_API_KEY` only if you explicitly want to use `load_entsoe_data.py` or `--data_source entsoe`

## Fastest path to a first submission

1. Clone the repository and install dependencies.
2. Copy `.env.example` to `.env`.
3. Fill in `ARENA_API_KEY`.
4. Run `python run_forecast_model.py --list_open_challenges`.
5. Generate one local payload.
6. Inspect the saved payload file.
7. Submit it with `python submit_forecast_to_energy_arena.py --payload_path test_payload.txt`.

Minimal commands:

```bash
python run_forecast_model.py --list_open_challenges
python run_forecast_model.py --target_date 27-03-2026 --challenge_id 1 --save_payload test_payload.txt
python submit_forecast_to_energy_arena.py --payload_path test_payload.txt
```

If you prefer one shortcut command after you understand the flow:

```bash
python master.py --target_date 27-03-2026 --challenge_id 1 --save_payload test_payload.txt
```

## What each script does

### `run_forecast_model.py`

Use this for the normal beginner workflow.

- lists currently open challenges
- resolves the selected challenge format
- builds a local payload with the starter model
- saves the payload to a local JSON file
- does not submit anything

### `submit_forecast_to_energy_arena.py`

Use this after you have checked the saved payload.

- loads a saved payload from disk
- validates its structure
- sends it to the Energy Arena API

### `master.py`

Use this if you want one command that does both steps in a row.

- generates the payload locally
- saves it
- submits it immediately afterwards

### `load_smard_data.py`

Use this if you want to inspect the raw SMARD input series used by the starter model for one target day.

### `load_entsoe_data.py`

Use this if you want to inspect the raw ENTSO-E input series used by the starter model for one target day.

## Quick start

### 1) Clone and install

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

```env
ARENA_API_KEY=your_arena_api_key_here
ARENA_API_BASE_URL=https://api.energy-arena.org
BASELINE_DATA_SOURCE=smard

# Optional only for ENTSO-E loading or --data_source entsoe
# ENTSOE_API_KEY=your_entsoe_api_key_here
```

All starter scripts read `.env` automatically.

### 3) Inspect open challenges

```bash
python run_forecast_model.py --list_open_challenges
```

The output shows:

- `Challenge ID`
- `Target`
- `Area`
- `Forecast Format`
- next submission deadline
- next target start

Use one of the printed `challenge_id` values in the next step.

### 4) Generate one local forecast payload

```bash
python run_forecast_model.py --target_date 27-03-2026 --challenge_id 1 --save_payload test_payload.txt
```

Notes:

- `target_date` must match the challenge's next target day
- the script resolves the required payload format automatically
- current point, quantile, and ensemble shapes are handled automatically
- current challenges are usually single-area, so you normally do not need `--area`
- the command saves the generated payload locally and does not submit yet

Optional ENTSO-E mode:

```bash
python run_forecast_model.py --target_date 27-03-2026 --challenge_id 1 --data_source entsoe --save_payload test_payload.txt
```

Use this only if you explicitly want the built-in baseline to use ENTSO-E instead of SMARD.

### 5) Submit the saved payload

```bash
python submit_forecast_to_energy_arena.py --payload_path test_payload.txt
```

Notes:

- this sends the saved JSON payload to Energy Arena via API POST
- the payload is stored first and evaluated later once realized target data is available
- after submitting, check the dashboard for the new entry and its current status

### 6) Optional combined shortcut

```bash
python master.py --target_date 27-03-2026 --challenge_id 1 --save_payload test_payload.txt
```

This runs generation and submission in one command. It is a convenience wrapper over `run_forecast_model.py` plus `submit_forecast_to_energy_arena.py`.

## Inspect the source data directly

Load the SMARD source series used by the starter model:

```bash
python load_smard_data.py --target_date 27-03-2026 --challenge_id 1
```

Load the ENTSO-E source series used by the starter model:

```bash
python load_entsoe_data.py --target_date 27-03-2026 --challenge_id 1
```

The ENTSO-E loader requires `ENTSOE_API_KEY`.

## Current starter-model behavior

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

The starter model reads the required quantiles or ensemble size directly from the live challenge detail endpoint.

## Integrate your own model

If you want to replace the built-in baseline with your own model:

1. Copy `custom_model_template.py` to `custom_model.py`.
2. Edit `transform_payload(...)`.
3. Generate one local payload with `run_forecast_model.py`.
4. Submit it with `submit_forecast_to_energy_arena.py`.
5. Only then enable daily automation.

Detailed guide:

- `MODEL_INTEGRATION.md`

## Daily automation

Run all currently open challenges:

```bash
python run_daily_submissions.py
```

Optional examples:

```bash
python run_daily_submissions.py --dry_run
python run_daily_submissions.py --target_date 27-03-2026
python run_daily_submissions.py --challenge_id 1
python run_daily_submissions.py --data_source entsoe
python run_daily_submissions.py --use_global_env
```

The batch runner fetches the open challenge list from the API and processes those challenge ids directly instead of relying on a hardcoded local list.

## Troubleshooting

Validate the local setup:

```bash
python run_forecast_model.py --check_setup
```

That checks local keys, API reachability, and custom-model loading.

## Scheduling

- Windows: `WINDOWS_TASK_SCHEDULER.md`
- Cross-platform notes: `SCHEDULE.md`
- Launchers: `run_daily_submissions.bat`, `run_daily_submissions.ps1`

## Repository layout

- `run_forecast_model.py` - generate one local payload with the starter model
- `submit_forecast_to_energy_arena.py` - submit a saved payload via API POST
- `master.py` - generate and submit in one command
- `load_smard_data.py` - inspect SMARD input data
- `load_entsoe_data.py` - inspect ENTSO-E input data
- `run_daily_submissions.py` - batch submission for open challenges
- `challenge_catalog.py` - challenge discovery helpers
- `custom_model_template.py` - starter hook for your own model
- `MODEL_INTEGRATION.md` - custom model guide
- `SCHEDULE.md` - scheduling reference
- `WINDOWS_TASK_SCHEDULER.md` - Windows Task Scheduler setup
- `.env.example` - local config template
- `requirements.txt` - dependencies
