# Windows Task Scheduler setup

This runs daily submissions at **11:30 CET/CEST** for all currently open
challenges.

The recommended wrapper writes logs to `.\logs\run_daily_submissions_*.log` and
keeps a copy at `.\logs\run_daily_submissions_latest.log`.
Generated payloads are archived under `.\submitted_payloads\challenge_<id>\`.

## Prerequisites

- Python installed
- virtual environment created with `python -m venv .venv`
- dependencies installed with `.venv\Scripts\python.exe -m pip install -r requirements.txt`
- local `.env` created in the repo folder

```bash
copy .env.example .env
```

Fill in:

- `ARENA_API_KEY`
- optional `ARENA_API_BASE_URL`
- optional `BASELINE_DATA_SOURCE=smard|entsoe`
- optional `ENTSOE_API_KEY` only for `entsoe`

## Step 1: Open Task Scheduler

1. Press `Win + R`
2. Run `taskschd.msc`
3. Click **Create Task...**

## Step 2: General tab

- Name: `Energy Arena daily submissions`
- Choose whether the task runs only when logged on or also when logged off

## Step 3: Trigger

1. Add new trigger
2. Type: Daily
3. Time: **11:30:00**
4. Repeat every: 1 day

## Step 4: Action

Recommended:

- Program/script: `C:\path\to\energy-arena-participate\run_daily_submissions.bat`
- Start in: `C:\path\to\energy-arena-participate`

Alternative:

- Program/script: `C:\path\to\energy-arena-participate\.venv\Scripts\python.exe`
- Add arguments: `run_daily_submissions.py`
- Start in: `C:\path\to\energy-arena-participate`

The wrapper is preferred because it keeps timestamped log files for every run.

Optional ENTSO-E mode:

- Add arguments: `run_daily_submissions.py --data_source entsoe`

## Step 5: Save and test

1. Save the task
2. Right-click the task and choose **Run**
3. Confirm a successful run in Task Scheduler history
4. Inspect `.\logs\run_daily_submissions_latest.log`
5. Inspect `.\submitted_payloads\challenge_<id>\` for the archived JSON payloads
6. Check the Energy Arena dashboard for resulting submissions
