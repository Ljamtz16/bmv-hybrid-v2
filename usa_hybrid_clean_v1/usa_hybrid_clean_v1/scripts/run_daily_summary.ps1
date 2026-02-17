param(
  [int]$Days = 1,
  [string]$MarketTz = 'America/New_York',
  [switch]$SendText,
  [switch]$SendFile,
  [string]$EnvFile = '.env'
)

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PY = Join-Path $ROOT '.venv/Scripts/python.exe'
$LOG = Join-Path $ROOT 'data/trading/predictions_log.csv'
$OUT = Join-Path $ROOT 'reports/trading/daily_summary.html'

Write-Host "[DAILY] Generando resumen diario..."
$argsList = @(
  (Join-Path $ROOT 'scripts/36_weekly_summary.py'),
  '--log', $LOG,
  '--out-html', $OUT,
  '--days', $Days,
  '--market-tz', $MarketTz,
  '--title', 'Daily Trading Summary',
  '--env-file', $EnvFile
)
if ($SendText) { $argsList += '--send-telegram' }
if ($SendFile) { $argsList += '--send-file' }

& $PY @argsList

if ($LASTEXITCODE -eq 0) {
  Write-Host "[DAILY] OK -> $OUT"
} else {
  Write-Host "[DAILY] Falló con código $LASTEXITCODE" -ForegroundColor Yellow
}
