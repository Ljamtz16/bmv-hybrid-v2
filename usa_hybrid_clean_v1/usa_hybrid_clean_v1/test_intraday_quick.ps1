# Test rápido del sistema intraday
# Valida componentes clave sin decoraciones

param(
    [string]$TestDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$TestTickers = "AMD,NVDA,TSLA,AAPL"
)

Write-Host "`n=== TEST SISTEMA INTRADAY ===" -ForegroundColor Cyan
Write-Host "Fecha: $TestDate" -ForegroundColor Yellow
Write-Host "Tickers: $TestTickers`n" -ForegroundColor Yellow

$passed = 0
$total = 0

# 1. Config
$total++
if (Test-Path "config\intraday.yaml") {
    Write-Host "[OK] Config exists" -ForegroundColor Green
    $passed++
} else {
    Write-Host "[FAIL] Config missing" -ForegroundColor Red
}

# 2. Carpetas
$total++
@("data\intraday", "reports\intraday", "models") | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -ItemType Directory -Path $_ -Force | Out-Null
    }
}
Write-Host "[OK] Folders ready" -ForegroundColor Green
$passed++

# 3. Download
Write-Host "`n[DOWNLOAD] 15m data..." -ForegroundColor Cyan
python scripts\00_download_intraday.py --date $TestDate --interval 15m --tickers $TestTickers
$total++
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Download" -ForegroundColor Green
    $passed++
} else {
    Write-Host "[FAIL] Download" -ForegroundColor Red
}

# 4. Features
Write-Host "`n[FEATURES] Calculating..." -ForegroundColor Cyan
python scripts\09_make_targets_intraday.py --date $TestDate --interval 15m
$total++
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Features" -ForegroundColor Green
    $passed++
} else {
    Write-Host "[FAIL] Features" -ForegroundColor Red
}

# 5. Model check
$total++
if (Test-Path "models\clf_intraday.joblib") {
    Write-Host "[OK] Model exists" -ForegroundColor Green
    $passed++
    $hasModel = $true
} else {
    Write-Host "[SKIP] Model not trained" -ForegroundColor Yellow
    Write-Host "       Train with: python scripts\10_train_intraday.py --start 2025-09-01 --end 2025-10-31" -ForegroundColor Gray
    $hasModel = $false
}

# 6. Inference (if model exists)
if ($hasModel) {
    Write-Host "`n[INFERENCE] Predicting..." -ForegroundColor Cyan
    python scripts\11_infer_and_gate_intraday.py --date $TestDate
    $total++
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Inference" -ForegroundColor Green
        $passed++
        
        # Show sample
        $forecastFile = "reports\intraday\$TestDate\forecast_intraday.parquet"
        if (Test-Path $forecastFile) {
            Write-Host "`nSample forecast:" -ForegroundColor Cyan
            python -c "import pandas as pd; df = pd.read_parquet('$forecastFile'); print(f'  Tickers: {df.ticker.nunique()}, Bars: {len(df)}, Prob_win range: [{df.prob_win.min():.3f}, {df.prob_win.max():.3f}]'); print(df.nlargest(3, 'prob_win')[['ticker', 'timestamp', 'prob_win', 'close']].to_string(index=False))"
        }
    } else {
        Write-Host "[FAIL] Inference" -ForegroundColor Red
    }
    
    # 7. Patterns
    Write-Host "`n[PATTERNS] Detecting..." -ForegroundColor Cyan
    python scripts\22_merge_patterns_intraday.py --date $TestDate
    $total++
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Patterns" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "[WARN] Patterns" -ForegroundColor Yellow
    }
    
    # 8. TTH (if model exists)
    if (Test-Path "models\tth_hazard_intraday.joblib") {
        Write-Host "`n[TTH] Predicting..." -ForegroundColor Cyan
        python scripts\39_predict_tth_intraday.py --date $TestDate --steps-per-day 26 --sims 500
        $total++
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] TTH" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "[FAIL] TTH" -ForegroundColor Red
        }
    } else {
        Write-Host "`n[SKIP] TTH model not trained" -ForegroundColor Yellow
        Write-Host "       Train with: python scripts\38_train_tth_intraday.py --start 2025-09-01 --end 2025-10-31" -ForegroundColor Gray
    }
    
    # 9. Trade Plan
    Write-Host "`n[PLAN] Generating..." -ForegroundColor Cyan
    python scripts\40_make_trade_plan_intraday.py --date $TestDate
    $total++
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Trade Plan" -ForegroundColor Green
        $passed++
        
        # Show plan
        $planFile = "reports\intraday\$TestDate\trade_plan_intraday.csv"
        if (Test-Path $planFile) {
            Write-Host "`nTrade Plan:" -ForegroundColor Cyan
            python -c "import pandas as pd; plan = pd.read_csv('$planFile'); print(f'  Total signals: {len(plan)}'); print(plan[['ticker', 'entry_price', 'prob_win', 'expected_pnl']].to_string(index=False)) if len(plan) > 0 else print('  (no executable signals)')"
        }
    } else {
        Write-Host "[FAIL] Trade Plan" -ForegroundColor Red
    }
}

# 10. Telegram (dry-run)
Write-Host "`n[TELEGRAM] Testing dry-run..." -ForegroundColor Cyan
python scripts\33_notify_telegram_intraday.py --date $TestDate --send-plan --dry-run
$total++
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Telegram dry-run" -ForegroundColor Green
    $passed++
} else {
    Write-Host "[WARN] Telegram dry-run" -ForegroundColor Yellow
}

# Summary
Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Passed: $passed / $total" -ForegroundColor $(if ($passed -eq $total) { "Green" } else { "Yellow" })

# Next steps
Write-Host "`n=== NEXT STEPS ===" -ForegroundColor Cyan

if (-not $hasModel) {
    Write-Host "1. Train models:" -ForegroundColor Red
    Write-Host "   python scripts\10_train_intraday.py --start 2025-09-01 --end 2025-10-31" -ForegroundColor Gray
    Write-Host "   python scripts\38_train_tth_intraday.py --start 2025-09-01 --end 2025-10-31`n" -ForegroundColor Gray
}

if (-not (Test-Path ".env")) {
    Write-Host "2. Configure Telegram:" -ForegroundColor Yellow
    Write-Host "   .\setup_telegram.ps1`n" -ForegroundColor Gray
}

Write-Host "3. Run full pipeline:" -ForegroundColor Green
Write-Host "   .\run_intraday.ps1 -Date $TestDate -NotifyTelegram`n" -ForegroundColor Gray

Write-Host "4. Register scheduler:" -ForegroundColor Green
Write-Host "   .\setup_intraday_scheduler.ps1`n" -ForegroundColor Gray

Write-Host "DONE`n" -ForegroundColor Cyan
