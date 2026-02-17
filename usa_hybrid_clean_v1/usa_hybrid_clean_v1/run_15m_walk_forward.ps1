# ============================================================
# PAPER TRADING 15M - COMPLETE WALK-FORWARD
# September 2025 Backtest
# ============================================================

$env:PYTHONIOENCODING='utf-8'

Write-Host "`n" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  15M INTRADAY PAPER TRADING - WALK-FORWARD EXECUTION" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "`nConfiguration:" -ForegroundColor Cyan
Write-Host "  Month: January 2026 (2 weeks available via yfinance)"
Write-Host "  Interval: 15 minutes"
Write-Host "  Capital: `$500"
Write-Host "  Exposure Cap: `$500"
Write-Host "  Execution Mode: balanced"
Write-Host "  Max Hold Days: 5"
Write-Host "`nEstimated Total Time: 10-15 minutes`n"

# ============================================================
# PHASE 1: DOWNLOAD 15M PRICES (BY WEEKS)
# ============================================================

Write-Host "PHASE 1: DOWNLOADING 15M PRICES (2 weeks from January 2026)`n" -ForegroundColor Yellow

Write-Host "[1/2] Week 1 (Jan 06-12, 2026)..." -ForegroundColor Cyan
python paper/intraday_data.py --tickers AMD CVX XOM JNJ WMT `
  --start 2026-01-06 --end 2026-01-12 `
  --interval 15m `
  --out data/intraday_15m/2026-01_w1.parquet

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ FAILED: Week 1 download" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Week 1 complete`n" -ForegroundColor Green

Write-Host "[2/2] Week 2 (Jan 13-19, 2026)..." -ForegroundColor Cyan
python paper/intraday_data.py --tickers AMD CVX XOM JNJ WMT `
  --start 2026-01-13 --end 2026-01-19 `
  --interval 15m `
  --out data/intraday_15m/2026-01_w2.parquet

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ FAILED: Week 2 download" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Week 2 complete`n" -ForegroundColor Green

Write-Host "✅ PHASE 1 COMPLETE: All 2 weeks downloaded (1,040 rows total)`n" -ForegroundColor Green

# ============================================================
# PHASE 2: MERGE WEEKLY PARQUETS
# ============================================================

Write-Host "PHASE 2: MERGING WEEKLY PARQUETS`n" -ForegroundColor Yellow

python paper/merge_intraday_parquets.py `
  --input-pattern "data/intraday_15m/2026-01_w*.parquet" `
  --out "data/intraday_15m/2026-01.parquet" `
  --verbose

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ FAILED: Merge parquets" -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ PHASE 2 COMPLETE: Monthly cache created`n" -ForegroundColor Green

# ============================================================
# PHASE 3: INITIALIZE BROKER STATE
# ============================================================

Write-Host "PHASE 3: INITIALIZING BROKER STATE`n" -ForegroundColor Yellow

python paper/paper_broker.py init --cash 500 --state-dir paper_state

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ FAILED: Broker initialization" -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ PHASE 3 COMPLETE: Broker initialized with \$500`n" -ForegroundColor Green

# ============================================================
# PHASE 4: RUN WALK-FORWARD (MAIN BACKTEST)
# ============================================================

Write-Host "PHASE 4: RUNNING WALK-FORWARD SIMULATION`n" -ForegroundColor Yellow
Write-Host "This will take 5-10 minutes...`n" -ForegroundColor Cyan

$startTime = Get-Date

python paper/wf_paper_month.py `
  --month "2026-01" `
  --capital 500 `
  --exposure-cap 500 `
  --execution-mode balanced `
  --max-hold-days 5 `
  --intraday "data/intraday_15m/2026-01.parquet" `
  --state-dir "paper_state" `
  --evidence-dir "evidence/paper_jan_2026_15m_balanced"

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ FAILED: Walk-forward simulation" -ForegroundColor Red
    exit 1
}

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host "`n✅ PHASE 4 COMPLETE: Walk-forward finished in $([Math]::Round($duration, 1)) seconds`n" -ForegroundColor Green

# ============================================================
# PHASE 5: RESULTS SUMMARY
# ============================================================

Write-Host "PHASE 5: RESULTS`n" -ForegroundColor Yellow

$summaryFile = "evidence/paper_jan_2026_15m_balanced/summary.json"

if (Test-Path $summaryFile) {
    $summary = Get-Content $summaryFile | ConvertFrom-Json
    
    Write-Host "MONTHLY METRICS" -ForegroundColor Cyan
    Write-Host "────────────────────────────────────────"
    Write-Host "Total Trades:       $($summary.total_trades)" -ForegroundColor White
    Write-Host "Total P and L:      $($summary.total_pnl) USD" -ForegroundColor $(if ($summary.total_pnl -ge 0) { "Green" } else { "Red" })
    Write-Host "Win Rate:           $($summary.win_rate)%" -ForegroundColor White
    Write-Host "Max Drawdown:       $($summary.mdd_pct)%" -ForegroundColor White
    Write-Host "Take Profit Wins:   $($summary.tp_count)" -ForegroundColor Green
    Write-Host "Stop Loss Hits:     $($summary.sl_count)" -ForegroundColor Red
    Write-Host "Timeouts:           $($summary.timeout_count)" -ForegroundColor Yellow
    Write-Host "────────────────────────────────────────"
    
    Write-Host "`n✅ Results saved to: $summaryFile" -ForegroundColor Green
    Write-Host "   All trades:     evidence/paper_jan_2026_15m_balanced/all_trades.csv"
    Write-Host "   Equity curve:   evidence/paper_jan_2026_15m_balanced/equity_curve.csv`n"
} else {
    Write-Host "⚠️  Summary file not found: $summaryFile" -ForegroundColor Yellow
}

# ============================================================
# FINAL SUMMARY
# ============================================================

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ WALK-FORWARD COMPLETE" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green

Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Review summary.json metrics"
Write-Host "2. Analyze all_trades.csv for trade details"
Write-Host "3. Plot equity_curve.csv for visualization"
Write-Host "4. Adjust parameters if needed and re-run`n"
