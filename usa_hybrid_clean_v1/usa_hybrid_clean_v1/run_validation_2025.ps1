# =============================================
# run_validation_2025.ps1
# Ejecuta el pipeline USA para 2025-01 .. 2025-09
# =============================================
param(
  [ValidateSet('rotation','master','file')]
  [string]$Universe = 'rotation',
  [string]$TickersFile = ''
)

$ROOT = (Get-Location).Path
$PY = "$ROOT\.venv\Scripts\python.exe"
$SCRIPTS = "$ROOT\scripts"
$FORECAST_DIR = "$ROOT\reports\forecast"

$months = @('2025-01','2025-02','2025-03','2025-04','2025-05','2025-06','2025-07','2025-08','2025-09')

# Descarga previa única (opcional) para evitar repetir por mes
if ($Universe -eq 'file' -and -not $TickersFile) {
  Write-Host "--Universe=file requiere --TickersFile"
  exit 1
}
if ($Universe -eq 'file') {
  & $PY scripts/download_us_prices.py --universe file --tickers-file $TickersFile
} elseif ($Universe -eq 'master') {
  & $PY scripts/download_us_prices.py --universe master
} else {
  & $PY scripts/download_us_prices.py --universe rotation
}

foreach ($m in $months) {
  Write-Host "============================================="
  Write-Host " Ejecutando pipeline USA para $m"
  Write-Host "============================================="

  # Pipeline principal para el mes
  if ($Universe -eq 'file' -and -not $TickersFile) {
    Write-Host "--Universe=file requiere --TickersFile"
    exit 1
  }
  # Pasamos Universe a run_pipeline_usa.ps1
  if ($Universe -eq 'file') {
    .\scripts\run_pipeline_usa.ps1 -Month $m -Universe file -TickersFile $TickersFile -AutoTune -SkipDownload
  } elseif ($Universe -eq 'master') {
    .\scripts\run_pipeline_usa.ps1 -Month $m -Universe master -AutoTune -SkipDownload
  } else {
    .\scripts\run_pipeline_usa.ps1 -Month $m -Universe rotation -AutoTune -SkipDownload
  }

  # Recalcular shares (opcional) ya no es necesario: el simulador emite shares/cash_used
  # & $PY $SCRIPTS\28_enforce_position_sizing.py --month $m --per-trade-cash 200

  # Generar resumen de duraciones (ya lo hace el pipeline), por redundancia puedes volver a invocarlo
  # & $PY $SCRIPTS\27_trades_durations.py --month $m --in-dir $FORECAST_DIR --out-dir $FORECAST_DIR
}

Write-Host "============================================="
Write-Host " Validacion enero-septiembre 2025 completada"
Write-Host "============================================="
