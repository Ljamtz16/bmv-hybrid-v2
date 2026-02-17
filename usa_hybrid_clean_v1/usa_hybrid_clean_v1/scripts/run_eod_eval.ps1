param(
  [string]$Notify = 'TP_SL_ONLY',
  [int]$MinSessions = 1,
  [string]$MarketTz = 'America/New_York',
  [string]$EnvFile = '.env'
)

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PY = Join-Path $ROOT '.venv/Scripts/python.exe'
$LOG = Join-Path $ROOT 'data/trading/predictions_log.csv'
$DAILY = Join-Path $ROOT 'data/us/ohlcv_us_daily.csv'

Write-Host "[EOD] Ejecutando evaluación EOD..."
& $PY (Join-Path $ROOT 'scripts/35_check_predictions_and_notify.py') `
  --log $LOG `
  --daily $DAILY `
  --market-tz $MarketTz `
  --notify $Notify `
  --min-sessions $MinSessions `
  --env-file $EnvFile

if ($LASTEXITCODE -eq 0) {
  Write-Host "[EOD] OK"
} else {
  Write-Host "[EOD] Falló con código $LASTEXITCODE" -ForegroundColor Yellow
}
