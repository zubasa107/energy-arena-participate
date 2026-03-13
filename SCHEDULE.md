# Scheduling daily submissions at 11:30 CET

Run one of the following every day at **11:30 CET** (before 12:00 deadline for the target day):

- **Windows:** Task Scheduler with `run_daily_submissions.bat` or `run_daily_submissions.ps1`
- **Linux/macOS:** cron with `run_daily_submissions.py`

## Key handling (recommended)

Use a local `.env` file in this repo:

```bash
cp .env.example .env
```

Set:

- `ENTSOE_API_KEY`
- `ARENA_API_KEY`
- optional `ARENA_API_BASE_URL`

`run_daily_submissions.py` and `submit_forecast.py` read `.env` automatically.
Global env vars for API keys are ignored by default; enable fallback with `--use_global_env`.

---

## Windows (Task Scheduler)

1. Open `taskschd.msc`
2. Create Task (not Basic Task)
3. Trigger: Daily at 11:30 (CET)
4. Action:
   - Program/script: `C:\path\to\energy-arena-participate\run_daily_submissions.bat`
   - Start in: `C:\path\to\energy-arena-participate`
5. Save and run once manually to test

Alternative action:

- Program/script: `python`
- Arguments: `run_daily_submissions.py`
- Start in: `C:\path\to\energy-arena-participate`

Optional probabilistic modes:

- `run_daily_submissions.py --include_quantiles`
- `run_daily_submissions.py --include_ensemble`

---

## Linux/macOS (cron)

1. Open crontab: `crontab -e`
2. Add:

```cron
30 11 * * * cd /path/to/energy-arena-participate && /usr/bin/python3 run_daily_submissions.py
```

Replace `/path/to/energy-arena-participate` and `/usr/bin/python3` with your paths.

If you intentionally want global env fallback, add `--use_global_env`.

If you want probabilistic submissions, append `--include_quantiles` or
`--include_ensemble`.

---

## Optional dry run

```bash
python run_daily_submissions.py --dry_run
```

Probabilistic dry runs:

```bash
python run_daily_submissions.py --include_quantiles --dry_run
python run_daily_submissions.py --include_ensemble --dry_run
```
