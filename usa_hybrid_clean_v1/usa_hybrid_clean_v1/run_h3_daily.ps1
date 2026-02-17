param(
  [Parameter(Mandatory=$true)]
  [string]$Date,
  [string]$Month
)

if (-not $Month) {
  $Month = ($Date.Substring(0,7))
}

Write-Host "=== H3 DAILY PIPELINE ===" -ForegroundColor Cyan
Write-Host "Date: $Date  |  Month: $Month" -ForegroundColor Gray

# 1) Update prices
Write-Host "[1/5] Downloading prices..." -ForegroundColor Yellow
python scripts\download_us_prices.py

# 2) Rebuild features
Write-Host "[2/5] Building features..." -ForegroundColor Yellow
python scripts\make_targets_and_eval.py

# 3) Inference
Write-Host "[3/5] Running inference for $Month (H3 WF thresholds)..." -ForegroundColor Yellow
python scripts\infer_and_gate.py --month $Month --min-prob 0.62 --min-yhat 0.06

# 4) Simulate with frozen WF policy params
Write-Host "[4/5] Simulating trades..." -ForegroundColor Yellow
python scripts\24_simulate_trading.py --month $Month --tp-pct 0.065 --sl-pct 0.008 --horizon-days 3 --per-trade-cash 400 --capital-initial 1200 --max-open 3 --position-active --simulate-results-out trades_detailed.csv

# 5) Status report
Write-Host "[5/5] Generating status report for $Date..." -ForegroundColor Yellow
python scripts\show_h3_status.py --month $Month --as-of $Date

Write-Host "=== DONE ===" -ForegroundColor Green
