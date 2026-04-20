# Scheduling daily submissions at 11:30 CET

Run one of the following every day at **11:30 CET/CEST**:

- **Windows:** Task Scheduler with `run_daily_submissions.bat` or `run_daily_submissions.ps1`
- **Linux/macOS:** cron with `run_daily_submissions.py`

## Key handling

Use a local `.env` file in this repo:

```bash
cp .env.example .env
```

Set:

- `ARENA_API_KEY`
- optional `ARENA_API_BASE_URL`
- optional `BASELINE_DATA_SOURCE=smard|entsoe`
- optional `ENTSOE_API_KEY` only for `entsoe`

`run_daily_submissions.py`, `run_forecast_model.py`, and
`submit_forecast_to_energy_arena.py` read `.env` automatically.
Global env vars for API keys are ignored by default; enable fallback with
`--use_global_env`.

## Windows

1. Open `taskschd.msc`
2. Create Task
3. Trigger: Daily at 11:30
4. Action:
   - Program/script: `C:\path\to\energy-arena-participate\run_daily_submissions.bat`
   - Start in: `C:\path\to\energy-arena-participate`
5. Save and run once manually

The wrapper scripts write logs to `.\logs\run_daily_submissions_*.log` and
refresh `.\logs\run_daily_submissions_latest.log` on each run.
Generated payloads are archived under `.\submitted_payloads\challenge_<id>\`.

Alternative:

- Program/script: `python`
- Arguments: `run_daily_submissions.py`
- Start in: `C:\path\to\energy-arena-participate`

Optional:

- `run_daily_submissions.py --data_source entsoe`
- `run_daily_submissions.py --challenge_id 1`

## Linux/macOS

1. Open crontab: `crontab -e`
2. Add:

```cron
30 11 * * * cd /path/to/energy-arena-participate && ./.venv/bin/python -u run_daily_submissions.py
```
If you intentionally want global env fallback, add `--use_global_env`.

If you want ENTSO-E instead of the default SMARD baseline, append
`--data_source entsoe`.

## Dry run

```bash
python run_daily_submissions.py --dry_run
```

Without `--target_start` or `--target_date`, the runner uses each selected
challenge's `next_target_start` from the open challenge API.

## Recommended Wrapper
You can alternatively use the wrapper script _run_daily_submissions.sh_ to handle submissions and logging.

1. Open crontab: `crontab -e`
2. Add:
```bash
30 11 * * * cd /path/to/energy-arena-participate && ./run_daily_submissions.sh
```