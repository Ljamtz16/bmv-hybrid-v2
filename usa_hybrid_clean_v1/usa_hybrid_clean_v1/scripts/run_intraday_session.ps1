# =============================================
# run_intraday_session.ps1
# Sesión completa de trading intradía:
# 1. Descarga precios actuales para tickers del plan
# 2. Lanza monitor en loop durante horas de mercado (9:30-16:00 NY)
# =============================================
param(
  [int]$IntervalSeconds = 300,
  [string]$Plan = "val\trade_plan.csv"
)

$ErrorActionPreference = 'Stop'
$ROOT = (Get-Location).Path
$PY = "$ROOT\.venv\Scripts\python.exe"

Write-Host "=== Sesión Intradía (Download + Monitor Loop) ===" -ForegroundColor Cyan
Write-Host "Plan: $Plan"
Write-Host "Intervalo monitor: $IntervalSeconds segundos"

# 1) Descarga inicial de precios
Write-Host "`n[1/2] Descargando precios intradía para tickers del plan..." -ForegroundColor Yellow
& $PY scripts\download_intraday_for_plan.py --plan $Plan --interval 15m --days 1

if ($LASTEXITCODE -ne 0) {
  Write-Host "[WARN] Descarga inicial falló, continuando con precios existentes..." -ForegroundColor Yellow
}

# 2) Loop de monitoreo durante sesión
Write-Host "`n[2/2] Iniciando monitor intradía (Ctrl+C para detener)..." -ForegroundColor Yellow

$endHourUTC = 21  # 16:00 NY = 21:00 UTC aprox (ajustar si DST cambia)
$startHourUTC = 14  # 09:30 NY = 14:30 UTC aprox

while ($true) {
  $utcNow = (Get-Date).ToUniversalTime()
  $hour = $utcNow.Hour
  
  # Verificar ventana de trading
  if ($hour -lt $startHourUTC) {
    Write-Host "[WAIT] Fuera de horario (antes de 14:30 UTC). Esperando..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 600  # Esperar 10 min
    continue
  }
  
  if ($hour -ge $endHourUTC) {
    Write-Host "[END] Fin de sesión (>=21:00 UTC). Deteniendo monitor." -ForegroundColor Cyan
    break
  }
  
  # Tick de monitor
  Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] Monitor tick...") -ForegroundColor Gray
  & $PY scripts\monitor_intraday.py --once
  
  # Refrescar precios cada N ticks (ej: cada 3 ticks = cada 15 min si interval=300)
  $script:tickCount = if ($null -eq $script:tickCount) { 1 } else { $script:tickCount + 1 }
  if ($script:tickCount % 3 -eq 0) {
    Write-Host "  [refresh] Descargando precios actualizados..." -ForegroundColor DarkCyan
    & $PY scripts\download_intraday_for_plan.py --plan $Plan --interval 15m --days 1 | Out-Null
  }
  
  Start-Sleep -Seconds $IntervalSeconds
}

Write-Host "`n✅ Sesión intradía finalizada." -ForegroundColor Green
