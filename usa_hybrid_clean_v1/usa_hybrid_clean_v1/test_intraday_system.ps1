<#
.SYNOPSIS
    Script de prueba completo para el sistema intraday.

.DESCRIPTION
    Ejecuta un test end-to-end del sistema intraday con datos de prueba.
    Valida cada componente individualmente y luego el pipeline completo.

.PARAMETER TestDate
    Fecha para testing (default: hoy).

.PARAMETER TestTickers
    Tickers para prueba (default: AMD,NVDA,TSLA,AAPL).

.PARAMETER SkipDownload
    Omite descarga si ya tienes datos.

.EXAMPLE
    .\test_intraday_system.ps1
    # Test completo con defaults

.EXAMPLE
    .\test_intraday_system.ps1 -TestDate 2025-11-01 -SkipDownload
    # Test con fecha específica, sin descargar
#>

param(
    [string]$TestDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$TestTickers = "AMD,NVDA,TSLA,AAPL",
    [switch]$SkipDownload
)

$ErrorActionPreference = "Continue"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  TEST SISTEMA INTRADAY - END-TO-END" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "[INFO] Fecha de prueba: $TestDate" -ForegroundColor Yellow
Write-Host "[INFO] Tickers: $TestTickers`n" -ForegroundColor Yellow

$testResults = @{}
$totalTests = 0
$passedTests = 0

# Función helper para test
function Test-Component {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Description
    )
    
    $script:totalTests++
    Write-Host "`n[$script:totalTests] Testing: $Name" -ForegroundColor Cyan
    Write-Host "    $Description" -ForegroundColor Gray
    
    Invoke-Expression $Command
    $result = $LASTEXITCODE
    
    if ($result -eq 0) {
        Write-Host "    ✓ PASS" -ForegroundColor Green
        $script:passedTests++
        $script:testResults[$Name] = "PASS"
        return $true
    } else {
        Write-Host "    ✗ FAIL (exit code: $result)" -ForegroundColor Red
        $script:testResults[$Name] = "FAIL"
        return $false
    }
}

# ============================================
# FASE 1: VERIFICACIÓN DE CONFIGURACIÓN
# ============================================
Write-Host "`n=== FASE 1: VERIFICACIÓN DE CONFIGURACIÓN ===" -ForegroundColor Magenta

# 1.1 Config file
$totalTests++
if (Test-Path "config\intraday.yaml") {
    Write-Host "[1] Config file: ✓ PASS" -ForegroundColor Green
    $passedTests++
    $testResults["Config"] = "PASS"
} else {
    Write-Host "[1] Config file: ✗ FAIL (no existe)" -ForegroundColor Red
    $testResults["Config"] = "FAIL"
}

# 1.2 Carpetas
$totalTests++
$requiredDirs = @("data\intraday", "reports\intraday", "models")
$allExist = $true
foreach ($dir in $requiredDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "    Creada carpeta: $dir" -ForegroundColor Yellow
    }
}
Write-Host "[2] Carpetas requeridas: ✓ PASS" -ForegroundColor Green
$passedTests++
$testResults["Folders"] = "PASS"

# ============================================
# FASE 2: DESCARGA DE DATOS (opcional)
# ============================================
if (-not $SkipDownload) {
    Write-Host "`n=== FASE 2: DESCARGA DE DATOS ===" -ForegroundColor Magenta
    
    Test-Component `
        -Name "Download 15m" `
        -Command "python scripts\00_download_intraday.py --date $TestDate --interval 15m --tickers $TestTickers" `
        -Description "Descarga velas 15m para $TestTickers"
} else {
    Write-Host "`n=== FASE 2: DESCARGA OMITIDA ===" -ForegroundColor Yellow
}

# ============================================
# FASE 3: FEATURES Y TARGETS
# ============================================
Write-Host "`n=== FASE 3: FEATURES Y TARGETS ===" -ForegroundColor Magenta

Test-Component `
    -Name "Features/Targets" `
    -Command "python scripts\09_make_targets_intraday.py --date $TestDate --interval 15m" `
    -Description "Calcula RSI, EMA, MACD, ATR, targets win/tte"

# ============================================
# FASE 4: MODELOS (verifica existencia)
# ============================================
Write-Host "`n=== FASE 4: VERIFICACIÓN DE MODELOS ===" -ForegroundColor Magenta

$totalTests++
$modelFile = "models\clf_intraday.joblib"
if (Test-Path $modelFile) {
    Write-Host "[*] Modelo clasificador: ✓ EXISTE" -ForegroundColor Green
    $passedTests++
    $testResults["Model_Exists"] = "PASS"
    $hasModel = $true
} else {
    Write-Host "[*] Modelo clasificador: ✗ NO EXISTE" -ForegroundColor Yellow
    Write-Host "    Para entrenar: python scripts\10_train_intraday.py --start 2025-09-01 --end 2025-10-31" -ForegroundColor Gray
    $testResults["Model_Exists"] = "SKIP"
    $hasModel = $false
}

# ============================================
# FASE 5: INFERENCIA (si hay modelo)
# ============================================
if ($hasModel) {
    Write-Host "`n=== FASE 5: INFERENCIA ===" -ForegroundColor Magenta
    
    Test-Component `
        -Name "Inference" `
        -Command "python scripts\11_infer_and_gate_intraday.py --date $TestDate" `
        -Description "Genera prob_win y aplica filtros básicos"
    
    # Verificar forecast generado
    $totalTests++
    $forecastFile = "reports\intraday\$TestDate\forecast_intraday.parquet"
    if (Test-Path $forecastFile) {
        Write-Host "[*] Forecast generado: ✓ PASS" -ForegroundColor Green
        $passedTests++
        $testResults["Forecast_File"] = "PASS"
        
        # Mostrar muestra
        Write-Host "`n    Muestra del forecast:" -ForegroundColor Cyan
        python -c @"
import pandas as pd
df = pd.read_parquet('$forecastFile')
print(f'    Tickers: {df.ticker.nunique()}')
print(f'    Barras: {len(df)}')
print(f'    Prob_win range: [{df.prob_win.min():.3f}, {df.prob_win.max():.3f}]')
print(f'\n    Top-3 señales:')
print(df.nlargest(3, 'prob_win')[['ticker', 'timestamp', 'prob_win', 'close', 'atr_pct']].to_string(index=False))
"@
    } else {
        Write-Host "[*] Forecast generado: ✗ FAIL" -ForegroundColor Red
        $testResults["Forecast_File"] = "FAIL"
    }
} else {
    Write-Host "`n=== FASE 5: INFERENCIA OMITIDA (sin modelo) ===" -ForegroundColor Yellow
}

# ============================================
# FASE 6: PATRONES CANDLESTICK
# ============================================
if ($hasModel -and (Test-Path "reports\intraday\$TestDate\forecast_intraday.parquet")) {
    Write-Host "`n=== FASE 6: PATRONES CANDLESTICK ===" -ForegroundColor Magenta
    
    Test-Component `
        -Name "Patterns" `
        -Command "python scripts\22_merge_patterns_intraday.py --date $TestDate" `
        -Description "Detecta Hammer, Doji, Engulfing, Morning Star, Pin Bar"
    
    # Mostrar patrones detectados
    Write-Host "`n    Patrones detectados:" -ForegroundColor Cyan
    python -c @"
import pandas as pd
df = pd.read_parquet('reports/intraday/$TestDate/forecast_intraday.parquet')
if 'pattern_score' in df.columns:
    patterns = df[df.pattern_score != 0][['ticker', 'timestamp', 'pattern_score', 'hammer', 'doji', 'engulfing_bull', 'engulfing_bear']].head(5)
    if len(patterns) > 0:
        print(patterns.to_string(index=False))
    else:
        print('    (no hay patrones significativos)')
else:
    print('    (columna pattern_score no existe)')
"@
} else {
    Write-Host "`n=== FASE 6: PATRONES OMITIDOS (sin forecast) ===" -ForegroundColor Yellow
}

# ============================================
# FASE 7: TTH INTRADAY
# ============================================
$totalTests++
$tthModelFile = "models\tth_hazard_intraday.joblib"
if (Test-Path $tthModelFile) {
    Write-Host "`n=== FASE 7: TTH INTRADAY ===" -ForegroundColor Magenta
    
    Test-Component `
        -Name "TTH_Prediction" `
        -Command "python scripts\39_predict_tth_intraday.py --date $TestDate --steps-per-day 26 --sims 500" `
        -Description "Predice ETTH y P(TP<SL) con Monte Carlo"
    
    # Mostrar métricas TTH
    Write-Host "`n    Métricas TTH:" -ForegroundColor Cyan
    python -c @"
import pandas as pd
df = pd.read_parquet('reports/intraday/$TestDate/forecast_intraday.parquet')
if 'etth_days' in df.columns:
    print(f'    ETTH medio: {df.etth_days.mean():.3f} días (~{df.etth_days.mean()*26:.1f} barras)')
    print(f'    P(TP<SL) medio: {df.p_tp_before_sl.mean():.2%}')
    top = df.nlargest(3, 'p_tp_before_sl')[['ticker', 'timestamp', 'etth_days', 'p_tp_before_sl', 'prob_win']]
    print(f'\n    Top-3 por P(TP<SL):')
    print(top.to_string(index=False))
else:
    print('    (columnas TTH no existen)')
"@
} else {
    Write-Host "`n=== FASE 7: TTH OMITIDO (modelo no entrenado) ===" -ForegroundColor Yellow
    Write-Host "    Para entrenar: python scripts\38_train_tth_intraday.py --start 2025-09-01 --end 2025-10-31" -ForegroundColor Gray
    $testResults["TTH_Model"] = "SKIP"
}

# ============================================
# FASE 8: PLAN DE TRADING
# ============================================
if ($hasModel) {
    Write-Host "`n=== FASE 8: PLAN DE TRADING ===" -ForegroundColor Magenta
    
    Test-Component `
        -Name "Trade_Plan" `
        -Command "python scripts\40_make_trade_plan_intraday.py --date $TestDate" `
        -Description "Aplica filtros, guardrails, ranking E[PnL]/ETTH"
    
    # Mostrar plan generado
    $planFile = "reports\intraday\$TestDate\trade_plan_intraday.csv"
    if (Test-Path $planFile) {
        Write-Host "`n    Plan de trading generado:" -ForegroundColor Cyan
        python -c @"
import pandas as pd
plan = pd.read_csv('$planFile')
if len(plan) > 0:
    print(f'    Total señales: {len(plan)}')
    print(f'\n    Ejecutables:')
    print(plan[['ticker', 'entry_price', 'prob_win', 'expected_pnl', 'capital_allocated']].to_string(index=False))
else:
    print('    (sin señales ejecutables)')
"@
    }
    
    # Mostrar mensaje Telegram
    $telegramFile = "reports\intraday\$TestDate\telegram_message.txt"
    if (Test-Path $telegramFile) {
        Write-Host "`n    Preview mensaje Telegram:" -ForegroundColor Cyan
        Get-Content $telegramFile | Select-Object -First 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    }
} else {
    Write-Host "`n=== FASE 8: PLAN OMITIDO (sin modelo) ===" -ForegroundColor Yellow
}

# ============================================
# FASE 9: TELEGRAM (dry-run)
# ============================================
Write-Host "`n=== FASE 9: TELEGRAM (DRY-RUN) ===" -ForegroundColor Magenta

Test-Component `
    -Name "Telegram_DryRun" `
    -Command "python scripts\33_notify_telegram_intraday.py --date $TestDate --send-plan --dry-run" `
    -Description "Test notificación sin enviar (dry-run)"

# ============================================
# RESUMEN FINAL
# ============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  RESUMEN DE PRUEBAS" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Total tests: $totalTests" -ForegroundColor White
Write-Host "Passed: $passedTests" -ForegroundColor Green
Write-Host "Failed: $($totalTests - $passedTests)" -ForegroundColor $(if ($totalTests -eq $passedTests) { "Green" } else { "Red" })
Write-Host "Success rate: $([math]::Round(($passedTests/$totalTests)*100, 1))%`n" -ForegroundColor White

Write-Host "Detalle por componente:" -ForegroundColor Yellow
foreach ($test in $testResults.GetEnumerator() | Sort-Object Name) {
    $color = switch ($test.Value) {
        "PASS" { "Green" }
        "FAIL" { "Red" }
        "SKIP" { "Yellow" }
    }
    Write-Host "  $($test.Name): $($test.Value)" -ForegroundColor $color
}

# ============================================
# PRÓXIMOS PASOS
# ============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  PRÓXIMOS PASOS" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

if (-not $hasModel) {
    Write-Host "1. ENTRENAR MODELOS (requerido):" -ForegroundColor Red
    Write-Host "   python scripts\10_train_intraday.py --start 2025-09-01 --end 2025-10-31" -ForegroundColor Gray
    Write-Host "   python scripts\38_train_tth_intraday.py --start 2025-09-01 --end 2025-10-31`n" -ForegroundColor Gray
}

if (-not (Test-Path ".env")) {
    Write-Host "2. CONFIGURAR TELEGRAM:" -ForegroundColor Yellow
    Write-Host "   .\setup_telegram.ps1`n" -ForegroundColor Gray
}

Write-Host "3. EJECUTAR PIPELINE COMPLETO:" -ForegroundColor Green
Write-Host "   .\run_intraday.ps1 -Date $TestDate -NotifyTelegram`n" -ForegroundColor Gray

Write-Host "4. REGISTRAR SCHEDULER (evaluaciones cada 15min):" -ForegroundColor Green
Write-Host "   .\setup_intraday_scheduler.ps1`n" -ForegroundColor Gray

if ($passedTests -eq $totalTests) {
    Write-Host "[SUCCESS] Sistema listo para operar!" -ForegroundColor Green
} else {
    Write-Host "[WARN] Completa los pasos pendientes antes de operar" -ForegroundColor Yellow
}

Write-Host ""
