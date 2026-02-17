# =============================================
# run_intraday.ps1
# =============================================
<#
.SYNOPSIS
Pipeline completo intraday para un día específico.

.DESCRIPTION
Ejecuta el pipeline completo de intraday trading:
1. Descarga datos 15m
2. Calcula features y targets
3. Genera forecast (inferencia)
4. Crea plan de trading
5. Opcionalmente notifica por Telegram

.PARAMETER Date
Fecha en formato YYYY-MM-DD (default: hoy)

.PARAMETER Interval
Intervalo de velas (default: 15m)

.PARAMETER Tickers
Lista de tickers separados por coma (default: usa tickers_master.csv)

.PARAMETER SkipDownload
Saltar descarga de datos (útil si ya existen)

.PARAMETER SkipFeatures
Saltar cálculo de features (útil si ya existen)

.PARAMETER NotifyTelegram
Enviar notificación a Telegram

.EXAMPLE
.\run_intraday.ps1 -Date 2025-11-03
.\run_intraday.ps1 -Date 2025-11-03 -Tickers "AMD,NVDA,TSLA,AAPL,MSFT" -NotifyTelegram
#>

param(
    [string]$Date = (Get-Date -Format 'yyyy-MM-dd'),
    [string]$Interval = "15m",
    [string]$Tickers = "",
    [switch]$SkipDownload,
    [switch]$SkipFeatures,
    [switch]$NotifyTelegram
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "  USA Hybrid Clean V1 - Intraday Pipeline" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Fecha: $Date"
Write-Host "Interval: $Interval`n"

# Activar entorno virtual si existe
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "[pipeline] Activando .venv..." -ForegroundColor Yellow
    & .venv\Scripts\Activate.ps1
}

# 1) Descarga de datos intraday
if (-not $SkipDownload) {
    Write-Host "`n[1/7] Descargando datos intraday..." -ForegroundColor Green
    
    if ($Tickers) {
        python scripts\00_download_intraday.py --date $Date --interval $Interval --tickers $Tickers
    } else {
        python scripts\00_download_intraday.py --date $Date --interval $Interval --tickers-file data\us\tickers_master.csv
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Descarga falló" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`n[1/7] Saltando descarga (--SkipDownload)" -ForegroundColor Yellow
}

# 2) Cálculo de features y targets
if (-not $SkipFeatures) {
    Write-Host "`n[2/7] Calculando features y targets..." -ForegroundColor Green
    
    python scripts\09_make_targets_intraday.py --date $Date --interval $Interval
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Features falló" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`n[2/7] Saltando features (--SkipFeatures)" -ForegroundColor Yellow
}

# 3) Inferencia (forecast)
Write-Host "`n[3/7] Generando forecast..." -ForegroundColor Green

python scripts\11_infer_and_gate_intraday.py --date $Date

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Inferencia falló" -ForegroundColor Red
    exit 1
}

# 4) Detección de patrones candlestick
Write-Host "`n[4/7] Detectando patrones candlestick..." -ForegroundColor Green

python scripts\22_merge_patterns_intraday.py --date $Date

if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Patrones falló, continuando..." -ForegroundColor Yellow
}

# 5) Predicción TTH (Time-to-Hit)
Write-Host "`n[5/7] Prediciendo TTH (ETTH, P(TP<SL))..." -ForegroundColor Green

python scripts\39_predict_tth_intraday.py --date $Date --steps-per-day 26 --sims 500

if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] TTH falló, continuando sin ETTH..." -ForegroundColor Yellow
}

# 6) Plan de trading
Write-Host "`n[6/7] Generando plan de trading..." -ForegroundColor Green

python scripts\40_make_trade_plan_intraday.py --date $Date

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Plan de trading falló" -ForegroundColor Red
    exit 1
}

# 7) Notificación Telegram (opcional)
if ($NotifyTelegram) {
    Write-Host "`n[7/7] Enviando notificación Telegram..." -ForegroundColor Green
    
    python scripts\33_notify_telegram_intraday.py --date $Date --send-plan
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] Notificación Telegram falló" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[7/7] Notificación Telegram omitida (-NotifyTelegram no especificado)" -ForegroundColor Gray
}

# Resumen final
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "  Pipeline completado" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Duración: $([math]::Round($duration, 2)) segundos"

# Mostrar resumen del plan si existe
$planFile = "reports\intraday\$Date\trade_plan_intraday.csv"
if (Test-Path $planFile) {
    $plan = Import-Csv $planFile
    $nTrades = $plan.Count
    Write-Host "Trades en plan: $nTrades" -ForegroundColor Green
    
    if ($nTrades -gt 0) {
        Write-Host "`nTickers: $($plan.ticker -join ', ')" -ForegroundColor Cyan
    }
}

Write-Host "`n"
