# Paper Trading 15m - Master Checklist

**Configuration:** 15m intraday | Capital $500 | Cap $500 | Balanced Mode | Max Hold 5 days

---

## ✅ PRE-FLIGHT CHECKLIST (Before You Start)

### System Checks
- [ ] Python 3.8+ installed
- [ ] pandas, numpy, yfinance installed: `pip list | grep -E "pandas|numpy|yfinance"`
- [ ] Core pipeline data generated (signals_with_gates.parquet, ohlcv_daily.parquet)
- [ ] paper_state/ directory exists or ready to initialize

### Validation Command
```powershell
$env:PYTHONIOENCODING='utf-8'
python paper/validate_setup.py --check all
```

Expected: ✅ ALL CHECKS PASSED

---

## 📥 PHASE 1: DOWNLOAD 15M PRICES (One-Time)

### What It Does
Downloads 1-hour price data from yfinance by weekly chunks (to avoid 60-day limit).

### Checklist
- [ ] Create data/intraday_15m/ directory
- [ ] Download Week 1 (Sep 01-07)
  ```powershell
  python paper/intraday_data.py --tickers AMD CVX XOM JNJ WMT --start 2025-09-01 --end 2025-09-07 --interval 15m --out data/intraday_15m/2025-09_w1.parquet
  ```
- [ ] Download Week 2 (Sep 08-14)
- [ ] Download Week 3 (Sep 15-21)
- [ ] Download Week 4 (Sep 22-30)
- [ ] Verify each week loaded correctly
  ```powershell
  python -c "import pandas as pd; df=pd.read_parquet('data/intraday_15m/2025-09_w1.parquet'); print(f'{len(df)} rows, {df[\"ticker\"].nunique()} tickers')"
  ```

### Expected Output
```
Week 1: ~2500 rows, 5 tickers, 2025-09-01 to 2025-09-07
Week 2: ~2500 rows, 5 tickers, 2025-09-08 to 2025-09-14
Week 3: ~2500 rows, 5 tickers, 2025-09-15 to 2025-09-21
Week 4: ~2500 rows, 5 tickers, 2025-09-22 to 2025-09-30
```

---

## 🔀 PHASE 2: MERGE WEEKLY PARQUETS (One-Time)

### What It Does
Combines 4 weekly parquets into 1 monthly file.

### Checklist
- [ ] Run merge script
  ```powershell
  python paper/merge_intraday_parquets.py --input-pattern "data/intraday_15m/2025-09_w*.parquet" --out "data/intraday_15m/2025-09.parquet" --verbose
  ```
- [ ] Verify merged cache
  ```powershell
  python -c "import pandas as pd; df=pd.read_parquet('data/intraday_15m/2025-09.parquet'); print(f'{len(df)} rows, {df[\"ticker\"].nunique()} tickers, {df[\"datetime\"].min()} to {df[\"datetime\"].max()}')"
  ```

### Expected Output
```
~10000 rows, 5 tickers, 2025-09-01 09:30:00 to 2025-09-30 16:00:00
```

---

## 🏦 PHASE 3: INITIALIZE BROKER STATE (One-Time per Experiment)

### What It Does
Creates persistent paper broker state with initial capital.

### Checklist
- [ ] Initialize broker with $500
  ```powershell
  python paper/paper_broker.py init --cash 500 --state-dir paper_state
  ```
- [ ] Verify initialization
  ```powershell
  python paper/paper_broker.py status --state-dir paper_state
  ```

### Expected Output
```
Equity: $500.00
Cash: $500.00
Unrealized P&L: $0.00
Realized P&L: $0.00
Open Positions: 0
```

---

## 📊 PHASE 4: WALK-FORWARD SEPTEMBER 2025 (Main Event)

### What It Does
Simulates the entire month day-by-day:
- For each trading day: generates trade_plan with T-1 data
- Validates each plan (asof_date, exposure)
- Simulates intraday 15m execution
- Aggregates metrics

### Checklist
- [ ] Validate setup before running
  ```powershell
  python paper/validate_setup.py --check all --intraday "data/intraday_15m/2025-09.parquet"
  ```
- [ ] Run walk-forward
  ```powershell
  python paper/wf_paper_month.py `
    --month "2025-09" `
    --capital 500 `
    --exposure-cap 500 `
    --execution-mode balanced `
    --max-hold-days 5 `
    --intraday "data/intraday_15m/2025-09.parquet" `
    --state-dir "paper_state" `
    --evidence-dir "evidence/paper_sep_2025_15m_balanced" `
    --verbose
  ```

### Expected Duration
**5-10 minutes** (20 trading days × subprocess + simulation)

### Expected Output (As It Runs)
```
[2025-09-01] Simulating (asof_date=2025-08-29)
  OK Trade plan generated for asof_date=2025-08-29
  5 trades to simulate
  PnL: $123.45 | TP: 3, SL: 2, TO: 0

[2025-09-02] Simulating (asof_date=2025-09-01)
  OK Trade plan generated
  4 trades to simulate
  PnL: $87.23 | TP: 2, SL: 2, TO: 0

... (18 more days)

=== MONTHLY SUMMARY ===
Month: 2025-09
Execution Mode: balanced
Total Trades: 87
Total P&L: $2,345.67
Win Rate: 62.5%
MDD: -12.3%
CAGR: 234.0%
TP: 54, SL: 28, TIMEOUT: 5
```

---

## 📋 PHASE 5: ANALYZE RESULTS

### Checklist
- [ ] Check monthly summary
  ```powershell
  python -c "import json; s=json.load(open('evidence/paper_sep_2025_15m_balanced/summary.json')); print(f'PnL: ${s[\"total_pnl\"]:.2f} | Win Rate: {s[\"win_rate\"]:.1f}% | MDD: {s[\"mdd_pct\"]:.1f}%')"
  ```
- [ ] Review all trades
  ```powershell
  python -c "import pandas as pd; df=pd.read_csv('evidence/paper_sep_2025_15m_balanced/all_trades.csv'); print(df[['ticker', 'entry_price', 'exit_price', 'pnl', 'outcome']].head(10))"
  ```
- [ ] Check equity curve
  ```powershell
  python -c "import pandas as pd; df=pd.read_csv('evidence/paper_sep_2025_15m_balanced/equity_curve.csv'); print(f'Start: ${df[\"equity\"].iloc[0]:.2f} | End: ${df[\"equity\"].iloc[-1]:.2f} | Peak: ${df[\"equity\"].max():.2f} | Trough: ${df[\"equity\"].min():.2f}')"
  ```
- [ ] Review daily breakdown
  ```powershell
  ls evidence/paper_sep_2025_15m_balanced/2025-09-*/day_report.json | ForEach { "$(Split-Path -Leaf $_): $(python -c \"import json; r=json.load(open('$_')); print(f\\\"PnL={r['pnl']:.2f}\\\")\")"}
  ```

---

## 🎯 PHASE 6: DAILY OPERATIONS (Ongoing)

### For Each Trading Day

#### Morning (Generate Plan)
- [ ] Verify today's asof_date is previous trading day
- [ ] Generate trade plan
  ```powershell
  # Today = 2026-01-16, asof_date = 2026-01-15
  python scripts/run_trade_plan.py `
    --forecast "data/daily/signals_with_gates.parquet" `
    --prices "data/daily/ohlcv_daily.parquet" `
    --out "val/trade_plan_2026-01-16.csv" `
    --month "2026-01" `
    --capital 500 `
    --exposure-cap 500 `
    --execution-mode balanced `
    --asof-date "2026-01-15"
  ```
- [ ] Validate plan
  ```powershell
  python paper/validate_setup.py --check trade-plan --trade-plan "val/trade_plan_2026-01-16.csv" --expected-asof-date "2026-01-15"
  ```

#### Intraday (Execute & Monitor)
- [ ] Execute trades
  ```powershell
  python paper/paper_executor.py --trade-plan "val/trade_plan_2026-01-16.csv" --state-dir "paper_state"
  ```
- [ ] Check status
  ```powershell
  python paper/paper_broker.py status --state-dir "paper_state"
  ```
- [ ] Monitor periodically (every 15-30 min)
  ```powershell
  python paper/paper_reconciler.py --state-dir "paper_state"
  ```

#### EOD (Mark-to-Market & Dashboard)
- [ ] Update prices
  ```powershell
  python paper/paper_reconciler.py --state-dir "paper_state"
  ```
- [ ] Generate dashboard
  ```powershell
  python dashboards/dashboard_trade_monitor.py --state-dir "paper_state" --out "val/dashboard_2026-01-16.html"
  ```
- [ ] Review dashboard
  ```powershell
  # Open in browser: val/dashboard_2026-01-16.html
  # Or serve: python -m http.server 7777 --directory val
  ```

---

## 🔍 VALIDATION COMMANDS (Anytime)

### Quick Health Check
```powershell
python paper/validate_setup.py --check all
```

### Deep Dive - Intraday Cache
```powershell
python -c "
import pandas as pd
df = pd.read_parquet('data/intraday_15m/2025-09.parquet')
print(f'Rows: {len(df):,}')
print(f'Tickers: {df[\"ticker\"].nunique()}')
print(f'Interval: 15m (approx {len(df) // (df[\"ticker\"].nunique() * 22)})')  # 22 trading days
print(f'Date range: {df[\"datetime\"].min()} to {df[\"datetime\"].max()}')
"
```

### Deep Dive - Broker State
```powershell
python -c "
import json, pandas as pd
state = json.load(open('paper_state/state.json'))
fills = pd.read_csv('paper_state/fills.csv')
print(f'Equity: ${state[\"cash\"] + sum(p[\"qty\"] * p[\"current_price\"] for p in state[\"positions\"].values()):.2f}')
print(f'Positions: {len(state[\"positions\"])}')
print(f'Fills: {len(fills)}')
print(f'Last fill: {fills[\"timestamp\"].iloc[-1] if len(fills) > 0 else \"None\"}')
"
```

### Deep Dive - Walk-Forward Results
```powershell
python -c "
import json, pandas as pd
summary = json.load(open('evidence/paper_sep_2025_15m_balanced/summary.json'))
trades = pd.read_csv('evidence/paper_sep_2025_15m_balanced/all_trades.csv')
print(f'Total Trades: {summary[\"total_trades\"]}')
print(f'Total PnL: ${summary[\"total_pnl\"]:.2f}')
print(f'Win Rate: {summary[\"win_rate\"]:.1f}%')
print(f'TP: {summary[\"tp_count\"]} | SL: {summary[\"sl_count\"]} | TO: {summary[\"timeout_count\"]}')
print(f'MDD: {summary[\"mdd_pct\"]:.1f}%')
print(f'Avg Win: ${summary[\"avg_win\"]:.2f} | Avg Loss: ${summary[\"avg_loss\"]:.2f}')
"
```

---

## ⚠️ TROUBLESHOOTING CHECKLIST

### "asof_date mismatch" Error
- [ ] Check that core pipeline was regenerated today
- [ ] Verify signals_with_gates.parquet has today's T-1 data
- [ ] Rerun core pipeline if needed

### "No files matching pattern" Error
- [ ] Verify weekly parquets exist: `ls data/intraday_15m/`
- [ ] Check filenames match pattern `2025-09_w*.parquet`
- [ ] Redownload weeks that are missing

### "yfinance download failed" Error
- [ ] Try downloading manually with verbose output
- [ ] Check internet connection
- [ ] Try smaller date range (3-5 days instead of 7)

### "Exposure exceeded" Warning
- [ ] Check trade_plan.csv has correct qty values
- [ ] Verify exposure-cap is set to 500
- [ ] Ensure capital is set to 500

### Dashboard Shows 0 Positions
- [ ] Run paper_executor first
- [ ] Check paper_state/ directory exists
- [ ] Verify positions.csv is not empty

---

## 📈 EXPECTED RESULTS (September 2025 Balanced)

Based on historical backtest patterns:

- **Total Trades:** 70-90 (avg 4-5/day)
- **Total P&L:** ±$1,500 to ±$3,000
- **Win Rate:** 55-65%
- **Max Drawdown:** -8% to -15%
- **CAGR:** 100%-300% (if positive)
- **TP/SL/TO Ratio:** ~60% TP, ~30% SL, ~10% TO

*Actual results will vary based on market conditions and signal quality.*

---

## 📝 NOTES

- **asof_date rule:** Previous US trading day (skip weekends, no holidays)
- **15m interval:** Limited to ~60 days per yfinance call (hence weekly downloads)
- **max-hold-days:** 5 calendar days (adjust based on your holding strategy)
- **execution-mode:** balanced (midpoint between fast and conservative)

---

## 🎯 SUCCESS CRITERIA

- [ ] All 4 weeks of data downloaded successfully
- [ ] Weekly parquets merged into monthly cache
- [ ] Broker state initialized with $500
- [ ] Walk-forward completes without errors
- [ ] summary.json shows metrics (trades, PnL, win rate)
- [ ] equity_curve.csv shows daily progression
- [ ] No validation errors (asof_date matches, exposure <= cap)

---

**Status:** ✅ Ready for 15m Intraday Operations  
**Last Updated:** January 18, 2026
