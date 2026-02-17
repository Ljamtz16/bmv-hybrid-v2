# =============================================
# schedule_intraday.ps1
# =============================================
<#
.SYNOPSIS
Scheduler para evaluación intraday cada 15 minutos durante horario de mercado.

.DESCRIPTION
Este script debe ser ejecutado por el Programador de Tareas cada 15 minutos.
Verifica horario de mercado y ejecuta evaluación TP/SL + notificaciones.

.PARAMETER Date
Fecha en formato YYYY-MM-DD (default: hoy)

.PARAMETER Interval
Intervalo de evaluación (default: 15m)

.PARAMETER ForceRun
Forzar ejecución incluso fuera de horario de mercado

.EXAMPLE
.\schedule_intraday.ps1
.\schedule_intraday.ps1 -Date 2025-11-03 -ForceRun
#>

param(
    [string]$Date = (Get-Date -Format 'yyyy-MM-dd'),
    [string]$Interval = "15m",
    [switch]$ForceRun
)

$ErrorActionPreference = "Continue"

# Función para convertir hora local a NY
function Get-NYTime {
    $nyTZ = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [System.TimeZoneInfo]::ConvertTime([DateTime]::Now, $nyTZ)
}

# Función para verificar si estamos en horario de mercado
function Test-MarketHours {
    param([DateTime]$nyTime)
    
    $dayOfWeek = $nyTime.DayOfWeek
    
    # Solo lunes-viernes
    if ($dayOfWeek -eq 'Saturday' -or $dayOfWeek -eq 'Sunday') {
        return $false
    }
    
    # 09:30 - 16:00 NY
    $marketOpen = New-TimeSpan -Hours 9 -Minutes 30
    $marketClose = New-TimeSpan -Hours 16 -Minutes 0
    $currentTime = $nyTime.TimeOfDay
    
    return ($currentTime -ge $marketOpen -and $currentTime -le $marketClose)
}

# Obtener hora NY
$nyTime = Get-NYTime
$isMarketHours = Test-MarketHours -nyTime $nyTime

Write-Host "[schedule_intraday] Hora NY: $($nyTime.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "[schedule_intraday] Mercado abierto: $isMarketHours"

# Verificar si debemos ejecutar
if (-not $isMarketHours -and -not $ForceRun) {
    Write-Host "[schedule_intraday] Fuera de horario de mercado. Saliendo." -ForegroundColor Yellow
    exit 0
}

# Activar entorno virtual
if (Test-Path ".venv\Scripts\Activate.ps1") {
    & .venv\Scripts\Activate.ps1
}

Write-Host "`n[schedule_intraday] Ejecutando evaluación TP/SL..." -ForegroundColor Green

# Ejecutar evaluación (genera alerts.txt)
python scripts\35_eval_tp_sl_intraday.py --date $Date --interval $Interval --notify

$evalResult = $LASTEXITCODE

if ($evalResult -eq 0) {
    Write-Host "[schedule_intraday] Evaluación completada exitosamente" -ForegroundColor Green
    
    # Verificar si hay alertas para enviar por Telegram
    $alertFile = "reports\intraday\$Date\alerts.txt"
    if (Test-Path $alertFile) {
        $alerts = Get-Content $alertFile -Tail 10
        if ($alerts.Count -gt 0) {
            Write-Host "`n[schedule_intraday] Alertas recientes:" -ForegroundColor Cyan
            $alerts | ForEach-Object { Write-Host "  $_" }
            
            # Enviar alertas a Telegram (si hay nuevas, respeta throttling)
            Write-Host "[schedule_intraday] Enviando alertas a Telegram..." -ForegroundColor Green
            python scripts\33_notify_telegram_intraday.py --date $Date --send-alerts
            
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[WARN] Notificación Telegram falló" -ForegroundColor Yellow
            }
        }
    }
} else {
    Write-Host "[schedule_intraday] ERROR en evaluación (exit code: $evalResult)" -ForegroundColor Red
}

Write-Host "`n[schedule_intraday] Completado @ $(Get-Date -Format 'HH:mm:ss')`n"
