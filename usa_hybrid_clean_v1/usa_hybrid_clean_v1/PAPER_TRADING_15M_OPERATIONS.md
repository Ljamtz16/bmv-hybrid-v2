# Paper Trading with 15m Intraday - Operational Guide

**Last Updated:** January 18, 2026  
**Configuration:** 15m intraday, capital $500, cap $500, balanced mode

---

## 🎯 QUICK START (TODAY)

### Step 1: Generate Trade Plan for Today

Supón que **hoy es 2026-01-16** (Thursday). Tu `asof_date` correcto es **2026-01-15** (Wednesday):

```powershell
$env:PYTHONIOENCODING='utf-8'

python scripts/run_trade_plan.py `
  --forecast "data/daily/signals_with_gates.parquet" `
  --prices   "data/daily/ohlcv_daily.parquet" `
  --out      "val/trade_plan_2026-01-16.csv" `
  --month    "2026-01" `
  --capital  500 `
  --exposure-cap 500 `
  --execution-mode balanced `
  --asof-date "2026-01-15"
```

**Verify the plan has correct asof_date:**

```powershell
python -c "import pandas as pd; df=pd.read_csv('val/trade_plan_2026-01-16.csv'); print('asof_date:', df['asof_date'].unique()); print('rows:', len(df)); print('exposure:', df['exposure'].sum() if 'exposure' in df else 'N/A')"
```

**Expected output:**
```
asof_date: ['2026-01-15']
rows: N  (number of trades)
exposure: XXX (should be <= 500)
```

### Step 2: Execute in Paper Broker

```powershell
python paper/paper_executor.py `
  --trade-plan "val/trade_plan_2026-01-16.csv" `
  --state-dir "paper_state" `
  --slippage-bps 5
```

### Step 3: Update Prices & Generate Dashboard

```powershell
python paper/paper_reconciler.py --state-dir "paper_state"

python dashboards/dashboard_trade_monitor.py `
  --state-dir "paper_state" `
  --out "val/dashboard.html"
```

### Step 4: View Dashboard

```powershell
# Start HTTP server
python -m http.server 7777 --directory val

# Then open in browser:
# http://localhost:7777/dashboard.html
```

---

## 📊 WALK-FORWARD SEPTEMBER 2025 (Backtesting)

### Phase 1: Download 15m Prices (By Week)

yfinance with 15m has a ~60-day historical limit, so download by weeks:

```powershell
$env:PYTHONIOENCODING='utf-8'

# Semana 1 (01-07)
python paper/intraday_data.py `
  --tickers AMD CVX XOM JNJ WMT `
  --start 2025-09-01 `
  --end 2025-09-07 `
  --interval 15m `
  --out "data/intraday_15m/2025-09_w1.parquet"

# Semana 2 (08-14)
python paper/intraday_data.py `
  --tickers AMD CVX XOM JNJ WMT `
  --start 2025-09-08 `
  --end 2025-09-14 `
  --interval 15m `
  --out "data/intraday_15m/2025-09_w2.parquet"

# Semana 3 (15-21)
python paper/intraday_data.py `
  --tickers AMD CVX XOM JNJ WMT `
  --start 2025-09-15 `
  --end 2025-09-21 `
  --interval 15m `
  --out "data/intraday_15m/2025-09_w3.parquet"

# Semana 4 (22-30)
python paper/intraday_data.py `
  --tickers AMD CVX XOM JNJ WMT `
  --start 2025-09-22 `
  --end 2025-09-30 `
  --interval 15m `
  --out "data/intraday_15m/2025-09_w4.parquet"
```

**Verify each week:**

```powershell
python -c "
import pandas as pd
for w in [1,2,3,4]:
    df = pd.read_parquet(f'data/intraday_15m/2025-09_w{w}.parquet')
    print(f'Week {w}: {len(df)} rows, {df[\"ticker\"].nunique()} tickers, {df[\"datetime\"].min()} to {df[\"datetime\"].max()}')
"
```

---

### Phase 2: Merge Weekly Parquets into Monthly

```powershell
# Option A: Use helper script
python paper/merge_intraday_parquets.py `
  --input-pattern "data/intraday_15m/2025-09_w*.parquet" `
  --out "data/intraday_15m/2025-09.parquet" `
  --verbose

# Option B: One-liner if you prefer
python -c "
import pandas as pd; import glob
files = sorted(glob.glob('data/intraday_15m/2025-09_w*.parquet'))
df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
df = df.sort_values('datetime').reset_index(drop=True)
df.to_parquet('data/intraday_15m/2025-09.parquet', index=False)
print(f'Merged {len(files)} files: {len(df)} rows, {df[\"datetime\"].min()} to {df[\"datetime\"].max()}')
"
```

**Verify merged cache:**

```powershell
python -c "
import pandas as pd
df = pd.read_parquet('data/intraday_15m/2025-09.parquet')
print(f'Total: {len(df)} rows')
print(f'Tickers: {df[\"ticker\"].nunique()}')
print(f'Date range: {df[\"datetime\"].min()} to {df[\"datetime\"].max()}')
print(f'Columns: {list(df.columns)}')
"
```

**Expected:**
```
Total: ~150000 rows
Tickers: 5
Date range: 2025-09-01 09:30:00 to 2025-09-30 16:00:00
Columns: ['datetime', 'ticker', 'open', 'high', 'low', 'close', 'volume']
```

---

### Phase 3: Initialize Broker State (One-Time)

```powershell
python paper/paper_broker.py init `
  --cash 500 `
  --state-dir "paper_state"
```

**Verify:**

```powershell
python paper/paper_broker.py status --state-dir "paper_state"
```

Output should show: `Equity: $500.00 | Cash: $500.00 | Open: 0`

---

### Phase 4: Run Walk-Forward (Day-by-Day Simulation)

This will:
1. For each trading day in September 2025:
   - Calculate `asof_date` (previous trading day)
   - Generate trade_plan with that asof_date
   - Validate the plan
   - Simulate intraday 15m execution
   - Save daily report
2. Aggregate all trades, metrics, equity curve

**Run:**

```powershell
python paper/wf_paper_month.py `
  --month "2025-09" `
  --capital 500 `
  --exposure-cap 500 `
  --execution-mode balanced `
  --max-hold-days 5 `
  --intraday "data/intraday_15m/2025-09.parquet" `
  --state-dir "paper_state" `
  --evidence-dir "evidence/paper_sep_2025_15m_balanced"
```

**This will take ~5-10 minutes** (20 trading days × subprocess calls + simulation).

---

### Phase 5: Review Results

```powershell
# Monthly summary stats
python -c "import json; print(json.dumps(json.load(open('evidence/paper_sep_2025_15m_balanced/summary.json')), indent=2))"

# View all trades
python -c "import pandas as pd; df=pd.read_csv('evidence/paper_sep_2025_15m_balanced/all_trades.csv'); print(df[['ticker', 'entry_price', 'exit_price', 'pnl', 'outcome']].tail(20))"

# Equity curve (daily snapshots)
python -c "import pandas as pd; df=pd.read_csv('evidence/paper_sep_2025_15m_balanced/equity_curve.csv'); print(df[['date', 'equity', 'unrealized', 'realized']].tail(10))"
```

---

## 🔍 VALIDATION CHECKLIST

### Before Walk-Forward

**Check 1: Intraday cache is valid**

```powershell
python -c "
import pandas as pd
df = pd.read_parquet('data/intraday_15m/2025-09.parquet')
assert 'datetime' in df.columns, 'Missing datetime'
assert 'ticker' in df.columns, 'Missing ticker'
assert 'open' in df.columns, 'Missing OHLC'
assert len(df) > 0, 'Empty cache'
print(f'✅ Cache valid: {len(df)} rows, {df[\"ticker\"].nunique()} tickers')
"
```

**Check 2: Broker state initialized**

```powershell
python -c "
import json
state = json.load(open('paper_state/state.json'))
assert state['cash'] == 500, 'Cash mismatch'
assert len(state['positions']) == 0, 'Should start with no positions'
print('✅ Broker state ready')
"
```

**Check 3: Core pipeline data exists**

```powershell
python -c "
import pandas as pd
signals = pd.read_parquet('data/daily/signals_with_gates.parquet')
prices = pd.read_parquet('data/daily/ohlcv_daily.parquet')
print(f'✅ Signals: {len(signals)} rows, latest date {signals[\"datetime\"].max()}')
print(f'✅ Prices: {len(prices)} rows, latest date {prices[\"datetime\"].max()}')
"
```

---

### During Walk-Forward

**Monitor progress** (the walk-forward prints day-by-day updates):

```
[2025-09-01] Simulating (asof_date=2025-08-29)
  OK Trade plan generated for asof_date=2025-08-29: evidence/paper_sep_2025_15m_balanced/2025-09-01/trade_plan.csv
  5 trades to simulate (asof_date=2025-08-29)
  PnL: $123.45 | TP: 3, SL: 2, TO: 0

[2025-09-02] Simulating (asof_date=2025-09-01)
  ...
```

---

### After Walk-Forward

**Check monthly summary:**

```powershell
python -c "
import json
summary = json.load(open('evidence/paper_sep_2025_15m_balanced/summary.json'))
print('=== MONTHLY SUMMARY ===')
print(f'Total Trades: {summary[\"total_trades\"]}')
print(f'Total P&L: ${summary[\"total_pnl\"]:.2f}')
print(f'Win Rate: {summary[\"win_rate\"]:.1f}%')
print(f'MDD: {summary[\"mdd_pct\"]:.2f}%')
print(f'CAGR: {summary[\"cagr\"]:.1f}%')
"
```

---

## 📋 EXAMPLE OUTPUT

### Trade Plan Validation

```powershell
# After generating trade_plan.csv, verify:
python -c "
import pandas as pd
df = pd.read_csv('val/trade_plan_2026-01-16.csv')
print(f'asof_date: {df[\"asof_date\"].unique()}')  # Should be ['2026-01-15']
print(f'Total trades: {len(df)}')
print(f'Exposure: {df[\"exposure\"].sum():.2f} / 500')  # Should be <= 500
print(f'Tickers: {df[\"ticker\"].unique()}')
"
```

**Good output:**
```
asof_date: ['2026-01-15']
Total trades: 4
Exposure: 485.50 / 500
Tickers: ['AMD' 'XOM' 'CVX' 'WMT']
```

**Bad output (don't proceed):**
```
asof_date: ['2026-01-14']  # ← WRONG DATE! Regenerate pipeline
```

---

### Walk-Forward Summary

```powershell
# View summary.json
type evidence\paper_sep_2025_15m_balanced\summary.json
```

**Example output:**
```json
{
  "month": "2025-09",
  "execution_mode": "balanced",
  "capital": 500,
  "exposure_cap": 500,
  "total_trades": 87,
  "total_pnl": 345.67,
  "final_equity": 845.67,
  "win_rate": 62.1,
  "avg_win": 12.34,
  "avg_loss": -8.56,
  "mdd_pct": -7.8,
  "cagr": 124.3,
  "tp_count": 54,
  "sl_count": 28,
  "timeout_count": 5
}
```

---

## ⚙️ TROUBLESHOOTING

### "asof_date mismatch"

**Error:**
```
[WARN] Validation failed: asof_date mismatch: expected 2026-01-15, got ['2026-01-14']
```

**Solution:** Your `signals_with_gates.parquet` hasn't been updated with today's data yet. Regenerate the core pipeline:

```powershell
# Run your daily core pipeline (00_download → 33_make_trade_plan)
# This should update signals_with_gates.parquet with new T-1 data
```

---

### "No files matching pattern"

**Error:**
```
[ERROR] No files matching pattern: data/intraday_15m/2025-09_w*.parquet
```

**Solution:** Check your downloaded files:

```powershell
ls data/intraday_15m/
# Should show: 2025-09_w1.parquet, 2025-09_w2.parquet, etc.
```

---

### "yfinance download failed"

**Error:**
```
[ERROR] Failed to download data: ...
```

**Solution:** yfinance may have rate limits. Try with delay:

```powershell
# Download with verbose output
python -c "
import yfinance as yf
df = yf.download('AMD', start='2025-09-01', end='2025-09-07', interval='15m', progress=True)
print(f'Downloaded {len(df)} candles')
"

# If it fails, try smaller date range
```

---

### "Equity curve doesn't match summary"

**Solution:** Calculate manually:

```powershell
python -c "
import pandas as pd
trades = pd.read_csv('evidence/paper_sep_2025_15m_balanced/all_trades.csv')
pnl = trades['pnl'].sum()
final_equity = 500 + pnl
print(f'Initial: 500')
print(f'Total PnL: {pnl:.2f}')
print(f'Final Equity: {final_equity:.2f}')
print(f'Trades: {len(trades)} | TP: {len(trades[trades[\"outcome\"]==\"TP\"])} | SL: {len(trades[trades[\"outcome\"]==\"SL\"])} | TO: {len(trades[trades[\"outcome\"]==\"TIMEOUT\"])}')
"
```

---

## 📝 NOTES

### About asof_date

- `asof_date` = **T-1 trading day** (the previous business day)
- If simulating **2025-09-10** (Wed), then `asof_date = 2025-09-09` (Tue)
- If simulating **2025-09-09** (Tue), then `asof_date = 2025-09-08` (Mon)
- Weekends are skipped automatically

### About 15m Intervals

- **yfinance limitation:** ~60 days max per download
- **Solution:** Download by weeks, then merge
- **Validation:** Always check `datetime` range in merged parquet

### About max-hold-days

- `--max-hold-days 5` = trades can stay open for up to 5 calendar days
- If TP/SL not hit within 5 days → TIMEOUT (exit next day at open)
- Adjust based on your risk tolerance:
  - **2-3 days:** More rotation, less holding risk
  - **5+ days:** Longer-term plays, capture bigger moves

---

## 🎯 NEXT STEPS

1. **Today:** Run quick workflow (Section "QUICK START")
2. **This Week:** Run walk-forward for September 2025
3. **Next:** Analyze results, iterate execution mode/parameters

---

**Last Updated:** January 18, 2026  
**Status:** ✅ Ready for 15m Intraday Operations
