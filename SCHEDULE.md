# Scheduling daily submissions at 11:30 CET

Run **one** of the following every day at **11:30 CET** (before the 12:00 deadline for the next target day).

- **Windows:** use **Task Scheduler** with `run_daily_submissions.bat` or `run_daily_submissions.ps1`.
- **Linux/macOS:** use **cron** with `run_daily_submissions.py`.

---

## Windows (Task Scheduler)

1. Open **Task Scheduler** (e.g. `taskschd.msc`).
2. **Create Task** (not “Create Basic Task” so you can set environment variables).
3. **General:** name e.g. “Energy Arena daily submissions”, run whether user is logged on or not (optional).
4. **Triggers:** New → **Daily**, repeat **once** at **11:30**.  
   - If your machine uses a different time zone, set the time so it equals **11:30 CET** (e.g. 11:30 if the PC is already on CET, or 10:30 UTC in winter / 09:30 UTC in summer for CET).
5. **Actions:** New → **Start a program**  
   - **Program/script:** `python` (or full path to `python.exe`)  
   - **Add arguments:** `run_daily_submissions.py`  
   - **Start in:** `C:\path\to\energy-arena-participate` (folder that contains `run_daily_submissions.py` and `submit_forecast.py`)

   **Or** use the batch file:  
   - **Program/script:** `C:\path\to\energy-arena-participate\run_daily_submissions.bat`  
   - **Start in:** `C:\path\to\energy-arena-participate`
6. **Environment variables for the task:**  
   In the same dialog, if your Task Scheduler supports “Start in” and an optional “Environment” / “Add arguments” section, you can configure the task to run with variables. Otherwise set them **system-wide** or **for your user**:  
   - `ENTSOE_API_KEY` = your ENTSO-E API key  
   - `ARENA_API_KEY` = your Arena API key  

   To set user env vars: **Settings → System → About → Advanced system settings → Environment Variables**. Add the two variables for your user (or System). The task will then see them when it runs.
7. **Conditions:** Uncheck “Start only if on AC” if you want it to run on battery.
8. Save the task. Run it once manually to test.

**Using PowerShell script instead of batch:**  
- **Program/script:** `powershell.exe`  
- **Add arguments:** `-NoProfile -ExecutionPolicy Bypass -File "C:\path\to\energy-arena-participate\run_daily_submissions.ps1"`  
- **Start in:** `C:\path\to\energy-arena-participate`  
Ensure `ENTSOE_API_KEY` and `ARENA_API_KEY` are set (user or system env, or inside the script if you hardcode them for testing only).

---

## Linux / macOS (cron)

1. Open crontab: `crontab -e`
2. Ensure the scheduler runs in **CET** or use a time that matches 11:30 CET, for example (runs at 11:30 in the server’s local time; if the server is in CET, this is 11:30 CET):

   ```cron
   30 11 * * * ENTSOE_API_KEY=xxx ARENA_API_KEY=yyy /usr/bin/python3 /path/to/energy-arena-participate/run_daily_submissions.py
   ```

   Or export the keys in your shell profile and run the script without inline env:

   ```cron
   30 11 * * * cd /path/to/energy-arena-participate && /usr/bin/python3 run_daily_submissions.py
   ```

   Replace `xxx` / `yyy` and `/path/to/energy-arena-participate` with your values. Use the full path to `python3` (e.g. from `which python3`).

---

## What gets submitted

- **Target date:** Tomorrow (in Europe/Berlin) when the script runs at 11:30 CET.
- **6 submissions:**  
  - `day_ahead_price` → DE_LU, AT (d-1)  
  - `day_ahead_load`  → DE_LU, AT (d-2)  
  - `day_ahead_solar` → DE_LU, AT (d-2)

Optional: run with `--dry_run` first to confirm payloads and target date without sending:

```bash
python run_daily_submissions.py --dry_run
```
