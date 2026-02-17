# =============================================
# run_intraday_monitor.ps1
# Lanza monitor_intraday en loop durante la sesión (NY 09:30-16:00)
# =============================================
param(
  [int]$IntervalSeconds = 300,
  [switch]$Once
)

$ErrorActionPreference = 'Stop'
$ROOT = (Get-Location).Path
$PY = "$ROOT\.venv\Scripts\python.exe"
Write-Host "=== Intraday Monitor ==="
Write-Host "Python: $PY"

if ($Once) {
  & $PY scripts/monitor_intraday.py --once
  exit $LASTEXITCODE
}

# Antes de iniciar, descargar snapshots intradía para los tickers del plan
Write-Host "[PRE] Descargando snapshots intradía para el plan..."
if (Test-Path "$ROOT\val\trade_plan.csv") {
  & $PY scripts/download_intraday_for_plan.py --plan $ROOT\val\trade_plan.csv --interval 5m --days 1
} else {
  Write-Host "[PRE] No se encontró val\trade_plan.csv; saltando descarga intradía"
}

# Loop hasta hora fin (16:00 NY -> 21:00 UTC aproximado; ajusta si tu TZ difiere)
$endHourUTC = 21

while ($true) {
  $utcNow = (Get-Date).ToUniversalTime()
  if ($utcNow.Hour -ge $endHourUTC) {
    Write-Host "[END] Fin de ventana intradía (>=21:00 UTC)" -ForegroundColor Cyan
    break
  }
  & $PY scripts/monitor_intraday.py --once
  Start-Sleep -Seconds $IntervalSeconds
}

Write-Host "Intraday monitor finalizado."