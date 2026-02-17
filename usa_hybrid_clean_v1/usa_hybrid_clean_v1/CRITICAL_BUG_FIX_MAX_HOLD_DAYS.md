# Critical Bug Fix: max_hold_days Logic Correction

**Date:** 2026-01-19  
**Status:** ✅ FIXED  
**Impact:** High – artificially inflated P&L and Win Rate by up to 76%

---

## Problem Statement

The intraday simulator incorrectly implemented `max_hold_days=2` logic:

### What was wrong:
1. **Calendar days, not trading sessions**: Used `timedelta(days=2)` which counts 48 hours regardless of weekends/holidays
2. **TIMEOUT extended to end of data**: If TP/SL never hit, trades stayed open until the last candle in the parquet file (often end of month)
3. **Falsified performance**: Trades from early December (e.g., 12-03) were closing at 12-30 EOD, not T+1 as intended

### Correct behavior:
- **Day 0**: Entry until EOD (market close)
- **Day 1**: Next trading day, full session
- **TIMEOUT**: Forced at close of Day 1 if no TP/SL hit

---

## Implementation

### Changes in `paper/intraday_simulator.py`:

1. **Extract unique trading dates from data**:
   ```python
   ticker_data["date_only"] = pd.to_datetime(ticker_data["datetime"]).dt.date
   unique_trade_dates = sorted(ticker_data["date_only"].unique())
   ```

2. **Calculate timeout date as Nth trading session**:
   ```python
   entry_date_idx = unique_trade_dates.index(entry_date)
   timeout_date_idx = entry_date_idx + (max_hold_days - 1)
   timeout_date = unique_trade_dates[timeout_date_idx]
   ```

3. **Force exit at EOD of timeout date**:
   ```python
   if candle_date == timeout_date and candle_dt == timeout_datetime:
       exit_price = close
       exit_time = candle_dt
       outcome = "TIMEOUT"
       break
   ```

4. **Removed fallback to last available candle**:
   - Old: `if exit_time is None: last_candle = ticker_data.iloc[-1]`
   - New: Strict enforcement of timeout window

---

## Impact Analysis

### December 2025 Old Universe (No Costs):

| Metric | BEFORE (Bug) | AFTER (Fixed) | Change |
|--------|--------------|---------------|---------|
| **Total P&L** | $44.66 | $10.57 | **-76.3%** ⚠️ |
| **Win Rate** | 55.9% | 45.8% | **-10.1pp** ⚠️ |
| **TP Trades** | 13 | 14 | +1 |
| **SL Trades** | 19 | 22 | +3 |
| **TIMEOUT Trades** | 27 | 23 | -4 |
| **MDD** | 1.59% | 1.58% | -0.01pp |

### TIMEOUT Hold Time Distribution (Fixed):

| Statistic | Calendar Days |
|-----------|--------------|
| **Mean** | 1.35 |
| **Median** | 1.0 |
| **Max** | 3 (weekend) |
| **Min** | 0 (same-day) |

**Before fix**: Many timeouts held 10-20+ calendar days (until month-end).

---

## Validation Results

### Test: `validate_max_hold_fix.py`

**Sample TIMEOUT trades (corrected):**
```
ticker  entry_time                 exit_time                  calendar_days  hold_hours
CVX     2025-12-03 14:30:00+00:00  2025-12-04 20:45:00+00:00  1              30.2
XOM     2025-12-04 14:30:00+00:00  2025-12-05 20:45:00+00:00  1              30.2
JNJ     2025-12-19 14:30:00+00:00  2025-12-22 20:45:00+00:00  3 (weekend)    78.2
```

**Compliance**:
- ✅ 20/23 TIMEOUT trades (87%) close within 1 trading day
- ✅ 2/23 (9%) close after weekend (3 calendar days, 2 trading days)
- ⚠️ 1/23 (4%) last-day-of-month edge case (no next session available)

---

## Next Steps

### Mandatory before production:
1. ✅ **Fix implemented and validated**
2. ⏳ **Re-run all A/B tests with corrected logic**:
   - December old/new universe (no costs)
   - December old/new universe (with costs)
   - January old/new universe (no costs)
   - January old/new universe (with costs)

3. ⏳ **Update all historical backtests**:
   - Oct-Nov 2025 results
   - Any other validation runs

4. ⏳ **Documentation update**:
   - Mark all pre-fix results as "DEPRECATED – inflated by hold-time bug"
   - Re-baseline all KPIs with corrected simulator

### Performance expectations post-fix:
- Lower P&L (more realistic stop-outs at T+1)
- Lower Win Rate (less time for positions to recover)
- Tighter MDD control (forced exits prevent deep drawdowns)
- More representative of 2-day swing trading strategy

---

## Conclusion

This was a **critical** bug that invalidated all prior backtest results. The corrected simulator now:

- Accurately models max_hold_days as trading sessions, not calendar time
- Forces TIMEOUT at EOD of Day (max_hold_days - 1)
- Prevents artificial profit inflation from extended holds

**All previous A/B comparisons (old vs new universe) are now obsolete** and must be re-run with the fixed simulator.

---

## Files Changed

- `paper/intraday_simulator.py`: Core fix (lines 140-230)
- `validate_max_hold_fix.py`: Validation script
- `CRITICAL_BUG_FIX_MAX_HOLD_DAYS.md`: This document

**Evidence directories (corrected runs):**
- `evidence/paper_dec_2025_FIXED_old/`
- (Pending: new universe, January, cost-adjusted variants)
