@echo off
REM Run daily Arena submissions (all 4 challenges x 2 areas).
REM Schedule this at 11:30 CET via Task Scheduler.
REM Put ENTSOE_API_KEY and ARENA_API_KEY in local .env (same folder).
REM Use --use_global_env only if you want fallback to system/user env vars.
REM Pass --include_quantiles or --include_ensemble if desired.

cd /d "%~dp0"
python run_daily_submissions.py %*
if errorlevel 1 exit /b 1
exit /b 0
