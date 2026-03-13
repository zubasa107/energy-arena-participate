# Windows Task Scheduler setup (11:30 CET)

This config runs daily submissions at **11:30 CET** for all 4 challenges and 2 areas.

## Prerequisites

- Python installed (`python` works in terminal)
- Repo dependencies installed: `pip install -r requirements.txt`
- Local `.env` created in repo folder:

```bash
copy .env.example .env
```

Fill in:

- `ENTSOE_API_KEY`
- `ARENA_API_KEY`
- optional `ARENA_API_BASE_URL`

The scripts read local `.env` automatically.  
Global env vars are optional fallback only (`--use_global_env`).

## Step 1: Open Task Scheduler

1. Press `Win + R`
2. Run `taskschd.msc`
3. Click **Create Task...**

## Step 2: General tab

- Name: `Energy Arena daily submissions`
- Choose whether task runs only when logged on or also when logged off
- Keep defaults unless your environment needs custom settings

## Step 3: Trigger

1. Add new trigger
2. Type: Daily
3. Time: **11:30:00**
4. Repeat every: 1 day

If machine timezone is not CET/CEST, set local time equivalent to 11:30 CET.

## Step 4: Action (recommended)

- Action: Start a program
- Program/script: `C:\path\to\energy-arena-participate\run_daily_submissions.bat`
- Start in: `C:\path\to\energy-arena-participate`

Alternative:

- Program/script: `python`
- Add arguments: `run_daily_submissions.py`
- Start in: `C:\path\to\energy-arena-participate`

Optional probabilistic mode:

- Add arguments: `run_daily_submissions.py --include_quantiles`
- or: `run_daily_submissions.py --include_ensemble`

## Step 5: Save and test

1. Save task
2. Right-click task → **Run**
3. Confirm successful run in Task Scheduler history / result code
4. Check Arena submissions for expected target day

## Quick summary

- Schedule: Daily 11:30 CET
- Action: `run_daily_submissions.bat` (or `python run_daily_submissions.py`)
- Start-in: repo folder
- Keys: local `.env` in repo
