# Run daily Arena submissions (all 4 challenges x 2 areas).
# Schedule at 11:30 CET (see README or SCHEDULE.md).
# Put ENTSOE_API_KEY and ARENA_API_KEY in local .env (same folder).
# Use --use_global_env only if you want fallback to system/user env vars.
# Pass --include_quantiles or --include_ensemble if desired.

Set-Location $PSScriptRoot
& python run_daily_submissions.py @args
exit $LASTEXITCODE
