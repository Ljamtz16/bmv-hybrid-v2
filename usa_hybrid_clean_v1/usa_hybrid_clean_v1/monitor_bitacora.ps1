# =============================================
# monitor_bitacora.ps1
# =============================================
# Monitor continuo de bitácora H3 cada 5 minutos
# Actualiza precios y detecta TP/SL automáticamente

param(
    [int]$IntervalMinutes = 5,
    [switch]$Continuous,
    [switch]$Once,
    [switch]$Silent
)

$ErrorActionPreference = "Continue"

# Configuración
$DailyPricesPath = "data\us\ohlcv_us_daily.csv"
$MarketOpenHour = 9
$MarketOpenMinute = 30
$MarketCloseHour = 16
$MarketCloseMinute = 0

function Test-MarketHours {
    $now = Get-Date
    
    # Verificar día de la semana (1=Lunes, 7=Domingo)
    if ($now.DayOfWeek -eq 'Saturday' -or $now.DayOfWeek -eq 'Sunday') {
        return $false
    }
    
    # Verificar hora
    $marketOpen = Get-Date -Hour $MarketOpenHour -Minute $MarketOpenMinute -Second 0
    $marketClose = Get-Date -Hour $MarketCloseHour -Minute $MarketCloseMinute -Second 0
    
    return ($now -ge $marketOpen -and $now -le $marketClose)
}

function Update-Prices {
    if (-not $Silent) {
        Write-Host "  Descargando precios actuales..." -ForegroundColor Cyan
    }
    
    try {
        python scripts\download_us_prices.py --universe master 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            if (-not $Silent) {
                Write-Host "  Precios actualizados" -ForegroundColor Green
            }
            return $true
        }
        else {
            if (-not $Silent) {
                Write-Host "  Advertencia: Error descargando precios, usando cache" -ForegroundColor Yellow
            }
            return $false
        }
    }
    catch {
        if (-not $Silent) {
            Write-Host "  Error: $_" -ForegroundColor Red
        }
        return $false
    }
}

function Update-Bitacora {
    try {
        python scripts\bitacora_excel.py --update
        return $LASTEXITCODE -eq 0
    }
    catch {
        if (-not $Silent) {
            Write-Host "  Error actualizando bitacora: $_" -ForegroundColor Red
        }
        return $false
    }
}

function Show-Header {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  MONITOR CONTINUO BITACORA H3" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Intervalo: $IntervalMinutes minutos" -ForegroundColor White
    
    if ($Continuous) {
        Write-Host "Modo: Continuo 24/7" -ForegroundColor White
    }
    else {
        Write-Host "Modo: Solo horario de mercado (9:30-16:00 ET, lun-vie)" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "Presiona Ctrl+C para detener" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

# Main
try {
    if ($Once) {
        # Ejecutar solo una vez
        Write-Host ""
        Write-Host "Ejecutando actualizacion unica..." -ForegroundColor Cyan
        Update-Prices
        Update-Bitacora
        Write-Host "Actualizacion completada" -ForegroundColor Green
        exit 0
    }
    
    Show-Header
    
    $iteration = 0
    
    while ($true) {
        $iteration++
        $now = Get-Date
        $timestamp = $now.ToString("yyyy-MM-dd HH:mm:ss")
        
        # Verificar si debemos ejecutar
        $shouldRun = $Continuous -or (Test-MarketHours)
        
        if ($shouldRun) {
            Write-Host ""
            Write-Host "[$timestamp] Actualizacion #$iteration" -ForegroundColor Yellow
            
            # Actualizar precios
            Update-Prices | Out-Null
            
            # Actualizar bitácora
            $success = Update-Bitacora
            
            if ($success) {
                Write-Host "  Proximo check en $IntervalMinutes minutos..." -ForegroundColor Gray
            }
            else {
                Write-Host "  Error en actualizacion, reintentando en $IntervalMinutes minutos..." -ForegroundColor Yellow
            }
        }
        else {
            # Fuera de horario
            if ($iteration -eq 1 -or ($iteration - 1) % 12 -eq 0) {
                Write-Host ""
                Write-Host "[$timestamp] Fuera de horario de mercado" -ForegroundColor DarkGray
                Write-Host "  Proxima apertura: 9:30 AM ET" -ForegroundColor DarkGray
            }
        }
        
        # Esperar
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}
catch {
    Write-Host ""
    Write-Host ""
    Write-Host "Monitor detenido" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Cyan
    exit 0
}
