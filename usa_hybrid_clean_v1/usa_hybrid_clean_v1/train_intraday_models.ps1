# Script para entrenar modelos intraday
# Ejecuta todo el pipeline de entrenamiento en secuencia

param(
    [string]$StartDate = "2025-09-01",
    [string]$EndDate = "2025-10-31",
    [string]$TickersFile = "data\us\tickers_master.csv",
    [int]$MaxTickers = 50,  # Limitar para prueba rápida
    [switch]$SkipDownload,
    [switch]$SkipFeatures
)

$ErrorActionPreference = "Continue"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ENTRENAMIENTO MODELOS INTRADAY" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Periodo: $StartDate -> $EndDate" -ForegroundColor Yellow
Write-Host "Tickers: $TickersFile (max $MaxTickers)`n" -ForegroundColor Yellow

# Leer tickers
$tickers = @()
if (Test-Path $TickersFile) {
    $tickersCsv = Import-Csv $TickersFile
    $tickers = ($tickersCsv | Select-Object -First $MaxTickers).ticker -join ","
    Write-Host "[INFO] Tickers seleccionados: $($tickers.Split(',').Count)" -ForegroundColor Cyan
} else {
    Write-Host "[ERROR] No se encuentra $TickersFile" -ForegroundColor Red
    exit 1
}

# ============================================
# FASE 1: DESCARGA DE DATOS HISTÓRICOS
# ============================================
if (-not $SkipDownload) {
    Write-Host "`n=== FASE 1: DESCARGA HISTÓRICA ===" -ForegroundColor Magenta
    Write-Host "Esto puede tomar 30-60 minutos dependiendo del número de tickers...`n" -ForegroundColor Yellow
    
    $startTime = Get-Date
    
    python scripts\00_download_intraday.py `
        --date $StartDate `
        --interval 15m `
        --tickers $tickers `
        --lookback-days 0
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Descarga falló" -ForegroundColor Red
        exit 1
    }
    
    # Descargar día por día (más confiable para rangos largos)
    Write-Host "`n[INFO] Descargando día por día para mejor cobertura..." -ForegroundColor Cyan
    
    $start = [datetime]::ParseExact($StartDate, "yyyy-MM-dd", $null)
    $end = [datetime]::ParseExact($EndDate, "yyyy-MM-dd", $null)
    $current = $start
    $downloaded = 0
    $failed = 0
    
    while ($current -le $end) {
        # Solo días de semana
        if ($current.DayOfWeek -ne [System.DayOfWeek]::Saturday -and 
            $current.DayOfWeek -ne [System.DayOfWeek]::Sunday) {
            
            $dateStr = $current.ToString("yyyy-MM-dd")
            Write-Host "  Descargando $dateStr..." -NoNewline
            
            python scripts\00_download_intraday.py `
                --date $dateStr `
                --interval 15m `
                --tickers $tickers `
                --lookback-days 5 | Out-Null
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host " OK" -ForegroundColor Green
                $downloaded++
            } else {
                Write-Host " FAIL" -ForegroundColor Red
                $failed++
            }
        }
        
        $current = $current.AddDays(1)
    }
    
    $elapsed = (Get-Date) - $startTime
    Write-Host "`n[FASE 1] Completado en $($elapsed.TotalMinutes.ToString('F1')) minutos" -ForegroundColor Green
    Write-Host "  Descargados: $downloaded días" -ForegroundColor Gray
    Write-Host "  Fallidos: $failed días`n" -ForegroundColor Gray
} else {
    Write-Host "`n=== FASE 1: DESCARGA OMITIDA ===" -ForegroundColor Yellow
}

# ============================================
# FASE 2: CALCULAR FEATURES Y TARGETS
# ============================================
if (-not $SkipFeatures) {
    Write-Host "`n=== FASE 2: FEATURES Y TARGETS ===" -ForegroundColor Magenta
    Write-Host "Calculando RSI, EMA, MACD, ATR, targets...`n" -ForegroundColor Yellow
    
    $startTime = Get-Date
    
    python scripts\09_make_targets_intraday.py `
        --start $StartDate `
        --end $EndDate `
        --interval 15m
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Features falló" -ForegroundColor Red
        exit 1
    }
    
    $elapsed = (Get-Date) - $startTime
    Write-Host "`n[FASE 2] Completado en $($elapsed.TotalMinutes.ToString('F1')) minutos`n" -ForegroundColor Green
} else {
    Write-Host "`n=== FASE 2: FEATURES OMITIDA ===" -ForegroundColor Yellow
}

# ============================================
# FASE 3: ENTRENAR CLASIFICADOR PROB_WIN
# ============================================
Write-Host "`n=== FASE 3: ENTRENAR CLASIFICADOR ===" -ForegroundColor Magenta
Write-Host "Random Forest + XGBoost para prob_win...`n" -ForegroundColor Yellow

$startTime = Get-Date

python scripts\10_train_intraday.py `
    --start $StartDate `
    --end $EndDate `
    --rolling-days 60

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Entrenamiento clasificador falló" -ForegroundColor Red
    exit 1
}

$elapsed = (Get-Date) - $startTime
Write-Host "`n[FASE 3] Completado en $($elapsed.TotalMinutes.ToString('F1')) minutos" -ForegroundColor Green

# Verificar modelo
if (Test-Path "models\clf_intraday.joblib") {
    Write-Host "[OK] Modelo guardado: models\clf_intraday.joblib" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Modelo no se guardó correctamente" -ForegroundColor Red
    exit 1
}

# ============================================
# FASE 4: ENTRENAR TTH (OPCIONAL)
# ============================================
Write-Host "`n=== FASE 4: ENTRENAR TTH ===" -ForegroundColor Magenta
Write-Host "Hazard discrete + Monte Carlo regressors...`n" -ForegroundColor Yellow

$startTime = Get-Date

python scripts\38_train_tth_intraday.py `
    --start $StartDate `
    --end $EndDate

if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Entrenamiento TTH falló, continuando..." -ForegroundColor Yellow
} else {
    $elapsed = (Get-Date) - $startTime
    Write-Host "`n[FASE 4] Completado en $($elapsed.TotalMinutes.ToString('F1')) minutos" -ForegroundColor Green
    
    # Verificar modelos TTH
    if (Test-Path "models\tth_hazard_intraday.joblib") {
        Write-Host "[OK] Modelo TTH guardado" -ForegroundColor Green
    }
}

# ============================================
# FASE 5: CREAR CALIBRACIÓN INICIAL
# ============================================
Write-Host "`n=== FASE 5: CALIBRACIÓN INICIAL ===" -ForegroundColor Magenta

$calibFile = "data\trading\tth_calibration_intraday.json"

if (-not (Test-Path $calibFile)) {
    @"
{
    "scale_tp": 1.0,
    "scale_sl": 1.0
}
"@ | Out-File -FilePath $calibFile -Encoding UTF8
    Write-Host "[OK] Creado $calibFile" -ForegroundColor Green
} else {
    Write-Host "[INFO] Ya existe $calibFile" -ForegroundColor Gray
}

# ============================================
# RESUMEN FINAL
# ============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ENTRENAMIENTO COMPLETADO" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Modelos entrenados:" -ForegroundColor Green
if (Test-Path "models\clf_intraday.joblib") {
    $size = (Get-Item "models\clf_intraday.joblib").Length / 1MB
    Write-Host "  [OK] clf_intraday.joblib ($($size.ToString('F1')) MB)" -ForegroundColor Green
}
if (Test-Path "models\scaler_intraday.joblib") {
    Write-Host "  [OK] scaler_intraday.joblib" -ForegroundColor Green
}
if (Test-Path "models\tth_hazard_intraday.joblib") {
    Write-Host "  [OK] tth_hazard_intraday.joblib" -ForegroundColor Green
}
if (Test-Path "models\tth_mc_mu_intraday.joblib") {
    Write-Host "  [OK] tth_mc_mu_intraday.joblib" -ForegroundColor Green
}
if (Test-Path "models\tth_mc_sigma_intraday.joblib") {
    Write-Host "  [OK] tth_mc_sigma_intraday.joblib" -ForegroundColor Green
}

Write-Host "`nPróximos pasos:" -ForegroundColor Cyan
Write-Host "  1. Test pipeline completo:" -ForegroundColor Yellow
Write-Host "     .\run_intraday.ps1 -Date 2025-10-31 -Tickers `"AMD,NVDA,TSLA`"`n" -ForegroundColor Gray

Write-Host "  2. Configurar Telegram:" -ForegroundColor Yellow
Write-Host "     .\setup_telegram.ps1`n" -ForegroundColor Gray

Write-Host "  3. Ejecutar con notificaciones:" -ForegroundColor Yellow
Write-Host "     .\run_intraday.ps1 -Date (Get-Date -Format `"yyyy-MM-dd`") -NotifyTelegram`n" -ForegroundColor Gray

Write-Host "  4. Registrar scheduler:" -ForegroundColor Yellow
Write-Host "     .\setup_intraday_scheduler.ps1`n" -ForegroundColor Gray

Write-Host "[SUCCESS] Sistema listo para operar!`n" -ForegroundColor Green
