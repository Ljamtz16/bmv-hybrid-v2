# =============================================
# run_daily_h3_forward.ps1
# =============================================
# Pipeline diario H3 con predicciones forward-looking
# Ejecutar cada da despus del cierre del mercado (post 4pm ET)

param(
    [string]$Month = "",
    [int]$RecentDays = 2,
    [int]$MaxOpen = 3,
    [double]$Capital = 1000.0,
    [switch]$SendTelegram,
    [switch]$SyncDrive,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Auto-detectar mes actual si no se especifica
if ([string]::IsNullOrEmpty($Month)) {
    $Month = (Get-Date).ToString("yyyy-MM")
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "PIPELINE H3 FORWARD-LOOKING - $Month" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Actualizar precios
Write-Host "[1/9] Actualizando precios del universo master..." -ForegroundColor Yellow
python scripts\download_us_prices.py --universe master
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error descargando precios" -ForegroundColor Red
    exit 1 
}

# 2. Regenerar features y targets
Write-Host "[2/9]  Generando features y targets..." -ForegroundColor Yellow
python scripts\make_targets_and_eval.py
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error generando features" -ForegroundColor Red
    exit 1 
}

# 3. Inferencia H3
Write-Host "[3/9]  Ejecutando inferencia H3..." -ForegroundColor Yellow
python scripts\infer_and_gate.py --month $Month --min-prob 0.56 --min-yhat 0.05
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error en inferencia" -ForegroundColor Red
    exit 1 
}

# 4. Detectar patrones tcnicos
Write-Host "[4/9]  Detectando patrones tcnicos..." -ForegroundColor Yellow
python scripts\20_detect_patterns.py
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error detectando patrones" -ForegroundColor Red
    exit 1 
}

# 5. Extraer features de patrones
Write-Host "[5/9]  Extrayendo features de patrones..." -ForegroundColor Yellow
python scripts\21_pattern_features.py
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error en pattern features" -ForegroundColor Red
    exit 1 
}

# 6. Mezclar forecast con patrones
Write-Host "[6/9]  Mezclando forecast con patrones..." -ForegroundColor Yellow
python scripts\22_merge_patterns_with_forecast.py --month $Month
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error mezclando forecast" -ForegroundColor Red
    exit 1 
}

# 7. Aplicar modelo TTH (Time-To-Hit)
Write-Host "[7/9]   Aplicando modelo TTH (Monte Carlo)..." -ForegroundColor Yellow
python scripts\39_predict_time_to_hit.py `
    --input "reports\forecast\$Month\forecast_with_patterns.csv" `
    --use-mc --mc-sims 500 --steps-per-day 1
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error en TTH" -ForegroundColor Red
    exit 1 
}

# 8. Generar trade plan forward-looking
Write-Host "[8/9]  Generando trade plan forward-looking..." -ForegroundColor Yellow
python scripts\40_make_trade_plan_with_tth.py `
    --input "reports\forecast\$Month\forecast_with_patterns_tth.csv" `
    --recent-days $RecentDays `
    --relax-if-empty `
    --strategy balanced `
    --max-signals 15 `
    --max-etth 2.5 `
    --min-p-tp-before-sl 0.65 `
    --min-prob 0.56 `
    --min-abs-yhat 0.05 `
    --atr-min 0.01 `
    --atr-max 0.08 `
    --cooldown-days 2 `
    --max-per-ticker 2 `
    --max-sector-share 0.6 `
    --max-open $MaxOpen `
    --capital $Capital
if ($LASTEXITCODE -ne 0) { 
    Write-Host " Error generando trade plan" -ForegroundColor Red
    exit 1 
}

# 9. Validar precios actuales
Write-Host "[9/9]  Validando precios del plan..." -ForegroundColor Yellow
python validate_plan_prices.py
if ($LASTEXITCODE -ne 0) { 
    Write-Host "  Warning: No se pudo validar precios" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " PIPELINE COMPLETADO" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

# Mostrar resumen
Write-Host " Archivos generados:" -ForegroundColor Cyan
Write-Host "   reports\forecast\$Month\trade_plan_tth.csv"
Write-Host "   reports\forecast\$Month\trade_candidates_tth.csv"
Write-Host "   reports\forecast\$Month\trade_plan_tth_telegram.txt"
Write-Host ""

# Enviar a Telegram si se solicita
if ($SendTelegram -and -not $DryRun) {
    Write-Host " Enviando plan a Telegram..." -ForegroundColor Yellow
    python scripts\send_plan_telegram.py "reports\forecast\$Month\trade_plan_tth_telegram.txt"
    if ($LASTEXITCODE -eq 0) {
        Write-Host " Plan enviado a Telegram" -ForegroundColor Green
    }
}

# Actualizar bitácora Excel
Write-Host ""
Write-Host "Actualizando bitacora Excel..." -ForegroundColor Yellow
python scripts\bitacora_excel.py --add-plan "reports\forecast\$Month\trade_plan_tth.csv"
if ($LASTEXITCODE -eq 0) {
    python scripts\bitacora_excel.py --update
    Write-Host " Bitacora actualizada" -ForegroundColor Green
}

# Sincronizar con Google Drive si se solicita
if ($SyncDrive -and -not $DryRun) {
    Write-Host ""
    Write-Host " Sincronizando con Google Drive..." -ForegroundColor Yellow
    .\sync_bitacora_to_gdrive.ps1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " Bitacora sincronizada con Drive" -ForegroundColor Green
    }
}

# Monitorear trades activos
Write-Host ""
Write-Host " Para monitorear trades activos, ejecuta:" -ForegroundColor Cyan
Write-Host "python scripts\35_check_predictions_and_notify.py --log data\trading\predictions_log.csv --daily data\us\ohlcv_us_daily.csv --notify TP_SL_ONLY"
Write-Host ""

