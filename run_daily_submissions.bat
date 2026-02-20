@echo off
REM Run daily Arena submissions (all 3 challenges x 2 areas).
REM Schedule this at 11:30 CET via Task Scheduler.
REM Set ENTSOE_API_KEY and ARENA_API_KEY in the task's environment or in system/user env.

cd /d "%~dp0"
python run_daily_submissions.py %*
if errorlevel 1 exit /b 1
exit /b 0
