# Paper Trading System - Quick Start Guide

## 1. ONE-TIME SETUP (5 minutes)

### Initialize broker state
```bash
python paper/paper_broker.py init --cash 1000 --state-dir paper_state
```

Creates:
- `paper_state/state.json` (persistent state)
- `paper_state/orders.csv` (empty orders log)
- `paper_state/fills.csv` (empty fills log)
- `paper_state/positions.csv` (empty positions)
- `paper_state/pnl_ledger.csv` (empty P&L ledger)

**Status check:**
```bash
python paper/paper_broker.py status --state-dir paper_state
```

---

## 2. DAILY WORKFLOW

### Step 1: Generate trade plan (via core USA_HYBRID_CLEAN_V1)
```bash
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan_balanced.csv \
  --capital 1000 \
  --exposure-cap 800 \
  --execution-mode balanced \
  --asof-date 2025-09-01
```

Output: `val/trade_plan_balanced.csv`

### Step 2: Execute trades in paper broker
```bash
python paper/paper_executor.py \
  --trade-plan val/trade_plan_balanced.csv \
  --state-dir paper_state \
  --slippage-bps 5
```

This:
- Places orders for qty>0 rows
- Simulates fills immediately (or use your own fill logic)
- Updates `paper_state/` with new positions

### Step 3: Check positions
```bash
python paper/paper_broker.py status --state-dir paper_state
```

Output:
```
Equity: $1227.95
Cash: $375.23
Unrealized P&L: +$52.15
Realized P&L: -$0.35
Open Positions: 3
```

### Step 4: Mark-to-market (update prices)
```bash
python paper/paper_reconciler.py \
  --state-dir paper_state \
  --cache-dir data/intraday_1h
```

This:
- Fetches latest prices (yfinance or cache)
- Updates unrealized P&L
- Logs all changes to `pnl_ledger.csv`

### Step 5: View dashboard
```bash
python dashboards/dashboard_trade_monitor.py \
  --state-dir paper_state \
  --out val/paper_dashboard.html
```

Then open `val/paper_dashboard.html` in browser:
```bash
# Windows
start val/paper_dashboard.html

# macOS
open val/paper_dashboard.html

# Linux
xdg-open val/paper_dashboard.html
```

**Dashboard features:**
- Auto-refresh every 60 seconds
- KPI cards: equity, cash, unrealized, realized, open count
- Open positions table with mark-to-market
- Recent fills table with outcomes
- Manual refresh button (purple button)

---

## 3. INTRADAY SIMULATION (OPTIONAL)

### Cache 1-hour prices (for Sep 2025)
```bash
python paper/intraday_data.py \
  --tickers AMD XOM CVX JNJ WMT \
  --start 2025-09-01 \
  --end 2025-09-30 \
  --interval 1h \
  --out data/intraday_1h/2025-09.parquet
```

Output: `data/intraday_1h/2025-09.parquet` (~5 MB)

### Run intraday simulator directly
```python
from paper.intraday_simulator import simulate_trades
import pandas as pd

# Load trade plan
trade_plan = pd.read_csv("val/trade_plan_intraday.csv")

# Load intraday cache
intraday_df = pd.read_parquet("data/intraday_1h/2025-09.parquet")

# Simulate
sim_trades = simulate_trades(
    trade_plan,
    intraday_df,
    max_hold_days=2,
    tp_pct=1.0,
    sl_pct=-0.4
)

# Results
print(sim_trades[["ticker", "entry_price", "exit_price", "pnl", "outcome"]])
```

---

## 4. WALK-FORWARD MONTHLY (ADVANCED)

### Run entire September 2025 day-by-day
```bash
python paper/wf_paper_month.py \
  --month 2025-09 \
  --capital 1000 \
  --exposure-cap 800 \
  --execution-mode balanced \
  --intraday data/intraday_1h/2025-09.parquet \
  --evidence-dir evidence/paper_sep_2025
```

Output directory structure:
```
evidence/paper_sep_2025/
├── 2025-09-01/
│   ├── trade_plan.csv
│   ├── audit.json
│   ├── sim_trades.csv
│   └── day_report.json
├── 2025-09-02/
│   └── ...
├── all_trades.csv (all month trades)
├── equity_curve.csv (daily equity)
├── summary.json (monthly stats)
└── summary.html (monthly report)
```

---

## 5. INTEGRATION TEST

### Run full test suite
```bash
python paper/test_paper_integration.py --verbose
```

Expected output:
```
✅ Directory Structure OK
✅ Intraday Data OK
✅ Intraday Simulator OK
✅ Metrics OK
✅ Paper Broker OK
✅ Paper Executor OK
✅ Paper Reconciler OK
✅ Dashboard OK
✅ WF Month OK
✅ Trade Plan Mock OK

RESULTS: 10/10 (100%)
✅ ALL TESTS PASSED
```

---

## 6. KEY FILES

| File | Purpose |
|------|---------|
| `paper/intraday_data.py` | Download 1h price cache |
| `paper/intraday_simulator.py` | Simulate trades vs candles |
| `paper/metrics.py` | Calculate stats (equity, MDD, CAGR) |
| `paper/paper_broker.py` | Persistent state management |
| `paper/paper_executor.py` | Execute trade_plan.csv |
| `paper/paper_reconciler.py` | Mark-to-market live |
| `dashboards/dashboard_trade_monitor.py` | Generate HTML dashboard |
| `paper/wf_paper_month.py` | Walk-forward monthly |
| `paper/test_paper_integration.py` | Integration tests |

---

## 7. EXECUTION MODES

### INTRADAY (ETTH ≤2.0 days)
```bash
python scripts/run_trade_plan.py ... --execution-mode intraday
```
**Rules:**
- Entry: Today
- Exit: Same day (16:00 EST) OR TP/SL hit
- TP targets: +0.5%, +0.8%, +1.2%
- SL: -0.4% hard stop
- Typical holding: 2-6 hours

### FAST (ETTH ≤3.5 days)
```bash
python scripts/run_trade_plan.py ... --execution-mode fast
```
**Rules:**
- Entry: Today or T+1
- Exit: Within 3-4 calendar days
- TP: Conservative
- SL: -0.5%

### BALANCED (ETTH ≤6.0 days) [DEFAULT]
```bash
python scripts/run_trade_plan.py ... --execution-mode balanced
```
**Rules:**
- Entry: T+0 or T+1
- Exit: Within 1-2 weeks
- TP/SL: Medium term
- Position size: Full allocation

### CONSERVATIVE (ETTH ≤10.0 days)
```bash
python scripts/run_trade_plan.py ... --execution-mode conservative
```
**Rules:**
- Entry: Flexible
- Exit: Within 2-3 weeks
- TP/SL: Wide targets
- Position size: Full allocation

---

## 8. TROUBLESHOOTING

### "No trades generated"
- Check `val/trade_plan_*.csv` exists
- Verify `--asof-date` is valid trading day
- Check capital > 0 and exposure_cap > 0

### "Dashboard shows 0 positions"
- Run `paper_executor.py` first
- Check `paper_state/positions.csv` not empty
- Verify `--state-dir` path is correct

### "Prices not updating"
- Run `paper_reconciler.py` manually
- Check internet connection (yfinance fetch)
- Verify cache `data/intraday_1h/*.parquet` exists

### "Integration tests fail"
- Verify all 8 modules exist in `paper/`
- Check Python path includes current directory
- Run `python -c "import sys; print(sys.path)"`

---

## 9. EXAMPLE: FULL DAY WORKFLOW

```bash
# 1. Generate balanced plan
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan.csv \
  --capital 1000 \
  --exposure-cap 800 \
  --execution-mode balanced \
  --asof-date 2025-09-01

# 2. Execute in paper
python paper/paper_executor.py \
  --trade-plan val/trade_plan.csv \
  --state-dir paper_state

# 3. Check status
python paper/paper_broker.py status --state-dir paper_state

# 4. Update prices
python paper/paper_reconciler.py \
  --state-dir paper_state \
  --cache-dir data/intraday_1h

# 5. View dashboard
python dashboards/dashboard_trade_monitor.py \
  --state-dir paper_state \
  --out val/dashboard.html

# Open in browser: val/dashboard.html
```

**Expected output flow:**
```
[PLAN] 4 trades generated ($650 exposure)
[EXEC] Executed 4 trades, $50 slippage
[BROKER] Equity $1000, Cash $350, Unrealized +$45
[RECON] Prices updated, MtM complete
[DASH] HTML generated with 4 open positions
```

---

## 10. OUTPUTS LOCATIONS

All generated files go to:
- **Trade plans:** `val/trade_plan_*.csv`
- **Dashboards:** `val/*.html`
- **Broker state:** `paper_state/*.json`, `paper_state/*.csv`
- **Price cache:** `data/intraday_1h/*.parquet`
- **Monthly evidence:** `evidence/paper_sep_2025/`

---

**Last Updated:** Jan 18, 2025
**System Status:** ✅ Production Ready
