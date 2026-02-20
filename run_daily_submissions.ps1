# Run daily Arena submissions (all 3 challenges x 2 areas).
# Schedule at 11:30 CET (see README or SCHEDULE.md).
# Set $env:ENTSOE_API_KEY and $env:ARENA_API_KEY, or use a .env file (e.g. with Get-Content .env).

Set-Location $PSScriptRoot
& python run_daily_submissions.py @args
exit $LASTEXITCODE
