#!/usr/bin/env bash

# Run daily Arena submissions for all currently open challenges.
# Schedule at 11:30 CET (see README or SCHEDULE.md).
# Put ARENA_API_KEY in local .env (same folder).
# The default baseline source is SMARD; ENTSOE_API_KEY is optional.
# Use --use_global_env only if you want fallback to system/user env vars.
# Pass --data_source entsoe only if you explicitly want ENTSO-E.
# Logs are written to .\logs\run_daily_submissions_*.log.

# Navigate to script dir
cd "$(dirname "$0")" || exit 1

# Create logs dir
LOG_DIR="$(pwd)/logs"
mkdir -p "$LOG_DIR"

# Timestamps
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# Log paths
LOG_PATH="$LOG_DIR/run_daily_submissions_$TIMESTAMP.log"
LATEST_LOG_PATH="$LOG_DIR/run_daily_submissions_latest.log"
echo "Writing log to $LOG_PATH"

# Executing run_daily_submissions.py and capturing exit code
.venv/bin/python -u run_daily_submissions.py "$@" 2>&1 | tee "$LOG_PATH"
EXIT_CODE=${PIPESTATUS[0]}

# Logging
cp "$LOG_PATH" "$LATEST_LOG_PATH"
echo "Latest log copied to $LATEST_LOG_PATH"
exit "$EXIT_CODE"
