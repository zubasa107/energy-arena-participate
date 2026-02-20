# How to set up Windows Task Scheduler for daily submissions (11:30 CET)

This guide sets up a Windows task that runs **every day at 11:30 CET** and submits forecasts for all 3 challenges and 2 areas (6 submissions).

---

## Prerequisites

- **Python** installed and on PATH (or note the full path to `python.exe`, e.g. `C:\Python314\python.exe`).
- **energy-arena-participate** folder with dependencies installed (`pip install -r requirements.txt`).
- Your **ENTSOE_API_KEY** and **ARENA_API_KEY** (you will set them as environment variables).

---

## Step 1: Set the API keys (Environment Variables)

The task will run without you logged in, so it needs the keys in the system or your user environment.

1. Press **Win + R**, type `sysdm.cpl`, press Enter.
2. Open the **Advanced** tab → **Environment Variables**.
3. Under **User variables** (or **System variables** if you prefer), click **New**:
   - **Variable name:** `ENTSOE_API_KEY`  
   - **Variable value:** your ENTSO-E API key  
   → OK.
4. Click **New** again:
   - **Variable name:** `ARENA_API_KEY`  
   - **Variable value:** your Arena API key  
   → OK.
5. Click **OK** on all dialogs.

If the task runs under your user account, **User variables** is enough. If it runs as “System” or another account, add the same variables under **System variables** (or create the task to run with your user account).

---

## Step 2: Open Task Scheduler

1. Press **Win + R**, type `taskschd.msc`, press Enter.
2. In the right-hand panel, click **Create Task…** (not “Create Basic Task”, so you can control user and settings).

---

## Step 3: General tab

1. **Name:** e.g. `Energy Arena daily submissions`
2. **Description:** (optional) e.g. `Submits d-1/d-2 forecasts for price, load, solar (DE_LU, AT) at 11:30 CET`
3. **Security options:**
   - Select **Run whether user is logged on or not** if you want it to run when nobody is at the PC.
   - Or **Run only when user is logged on** to use your current session (simpler; env vars are definitely yours).
4. **Configure for:** Windows 10/11 (or your OS).
5. Leave the rest as default. Do **not** check “Run with highest privileges” unless you have a reason.

---

## Step 4: Triggers tab

1. Click **New…**
2. **Begin the task:** **On a schedule**
3. **Settings:** **Daily**
4. **Start:** pick **today** (or any date); set **Time** to **11:30:00**.
5. **Recur every:** **1** days.
6. **Enabled** is checked.
7. **Repeat task every:** leave **disabled** (we want once per day at 11:30).
8. If your PC is already in **CET (Central European Time)**, 11:30 here = 11:30 CET. If the PC is in another time zone, set the time so that it corresponds to 11:30 CET (e.g. 10:30 if you are in UTC+1 and want 11:30 in CET).
9. Click **OK**.

---

## Step 5: Actions tab

1. Click **New…**
2. **Action:** **Start a program**
3. Choose **one** of the two options below.

### Option A — Using the batch file (recommended)

- **Program/script:**  
  `C:\Arbeitsordner\00_benchmark_arena\energy-arena-participate\run_daily_submissions.bat`  
  *(Replace with the full path to your `energy-arena-participate` folder if different.)*
- **Add arguments:** leave **empty**
- **Start in:**  
  `C:\Arbeitsordner\00_benchmark_arena\energy-arena-participate`  
  *(Same folder as above.)*

### Option B — Using Python directly

- **Program/script:**  
  `python`  
  Or full path, e.g. `C:\Python314\python.exe`
- **Add arguments:**  
  `run_daily_submissions.py`
- **Start in:**  
  `C:\Arbeitsordner\00_benchmark_arena\energy-arena-participate`  
  *(Full path to the folder that contains `run_daily_submissions.py` and `submit_forecast.py`.)*

4. Click **OK**.

---

## Step 6: Conditions tab (optional)

- If the PC is a laptop: **uncheck** “Start the task only if the computer is on AC power” if you want it to run on battery as well.
- Adjust “Wake the computer to run this task” if you need the task to run when the PC is in sleep (optional).

---

## Step 7: Settings tab (optional)

- **Allow task to be run on demand** — leave checked so you can run it manually for testing.
- **If the task fails, restart every:** optional (e.g. 10 minutes, 3 times) if you want automatic retries.

---

## Step 8: Save and test

1. Click **OK** to create the task. Enter your Windows password if prompted (for “Run whether user is logged on or not”).
2. In Task Scheduler, find **Energy Arena daily submissions** in the task list.
3. **Right‑click** the task → **Run**. Check that it runs without errors.
4. Optionally open **History** (or **Last Run Result**) to confirm “The operation completed successfully (0x0)”.

---

## Checking that it worked

- In the Arena (e.g. https://api.energy-arena.org or the Arena front end), check that new submissions appear for the expected target day (tomorrow).
- You can also run the script once from a command prompt to see the same behaviour:
  ```cmd
  cd C:\Arbeitsordner\00_benchmark_arena\energy-arena-participate
  run_daily_submissions.bat
  ```

---

## Summary

| Setting        | Value |
|----------------|--------|
| **Schedule**   | Daily at 11:30 (CET) |
| **Action**     | `run_daily_submissions.bat` (or `python run_daily_submissions.py`) |
| **Start in**   | Your `energy-arena-participate` folder |
| **Env vars**   | `ENTSOE_API_KEY`, `ARENA_API_KEY` (user or system) |

After this, the task will run every day at 11:30 and submit the 6 forecasts (price, load, solar × DE_LU, AT) for the next target day.
