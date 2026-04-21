# Run daily Arena submissions for all currently open challenges.
# Schedule at 11:30 CET (see README or SCHEDULE.md).
# Put ARENA_API_KEY in local .env (same folder).
# The default baseline source is SMARD; ENTSOE_API_KEY is optional.
# Use --use_global_env only if you want fallback to system/user env vars.
# Pass --data_source entsoe only if you explicitly want ENTSO-E.
# Logs are written to .\logs\run_daily_submissions_*.log.

Set-Location $PSScriptRoot
$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$timestamp = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss_fff"), $PID
$logPath = Join-Path $logDir "run_daily_submissions_$timestamp.log"
$latestLogPath = Join-Path $logDir "run_daily_submissions_latest.log"

function Quote-CmdArg {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }
    if ($Value -match '[\s"&^|<>]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$commandParts = @($venvPython, "-u", "run_daily_submissions.py") + $args
$cmdLine = (($commandParts | ForEach-Object { Quote-CmdArg $_ }) -join " ") + " 2>&1"

Write-Host "Writing log to $logPath"
& cmd.exe /d /c $cmdLine | Tee-Object -FilePath $logPath
$exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }

Copy-Item -Path $logPath -Destination $latestLogPath -Force
Write-Host "Latest log copied to $latestLogPath"
exit $exitCode
