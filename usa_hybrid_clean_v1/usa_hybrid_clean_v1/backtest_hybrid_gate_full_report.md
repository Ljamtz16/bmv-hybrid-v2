# HYBRID GATE BACKTEST REPORT - FULL OOS WINDOW
**Date:** 2026-01-20  
**Period:** 2024-02-21 to 2026-01-15 (476 trading days)  
**Tickers:** PFE, CVX, AMD, XOM (selected by hybrid gate = MC 60% + Signal Quality 40%)

## Configuration
- **TP Target:** 1.6%
- **SL Stop:** 1.0%  
- **Max Hold:** 2 days
- **Capital:** $1,000
- **Max Positions:** 5
- **Entry Rule:** Market open only, max 1 entry per ticker per day, prob_win > 0.55

## Results Summary

| Metric | Value | Assessment |
|--------|-------|-----------|
| **Total P&L** | -$37.82 | ❌ Loss |
| **Return** | -3.78% | ❌ Negative |
| **Final Balance** | $962.18 | Below initial |
| **Total Trades** | 21 | Very few |
| **Win Rate** | 9.5% | ❌ Extremely low |
| **Wins** | 2 | |
| **Losses** | 19 | |
| **Avg P&L/Trade** | -$1.80 | Negative average |
| **Profit Factor** | 0.07x | ❌ Severe risk/reward skew |
| **TP Hits** | 2 (9.5%) | |
| **SL Hits** | 19 (90.5%) | |

## Key Issues Identified

### 1. Forecast Calibration Problem
The generated `forecast_prob_win` from `generate_prob_win_forecast.py` is **poorly calibrated**:
- Expected P(win) based on forecast: ~50-55% (threshold used)
- Actual observed P(win): ~10% in backtest
- Root cause: Logistic regression model trained on synthetic TP/SL labels (forward-looking labels) does not reflect actual trading outcomes

### 2. Ticker Selection
The hybrid gate selected **PFE, CVX, AMD, XOM**:
- **MC Scores (normalized):** 
  - PFE: 0.8595 / -0.6626 (best)
  - CVX: 1.0000 / -0.1239 (highest absolute MC)
  - AMD: 0.5864 / -1.7095 (worst MC)
  - XOM: 0.9562 / -0.2916
- Signal quality scores are low across the board (0.06 - 0.17)
- These tickers appear to be statistically poor for TP 1.6% / SL 1.0% on intraday timeframe

### 3. Parameter Mismatch
TP:SL ratio of 1.6:1 requires WR > 38% to break even. However:
- Actual WR observed: 9.5% (catastrophically low)
- Even with WR = 48.6% (without prob_win filter), strategy was -35% return on 1664 trades

## Recommendations

### Option A: Recalibrate Forecast
1. Train prob_win model on **actual historical trading outcomes** (not synthetic labels)
2. Use 2-year historical data to calibrate true win probabilities per ticker
3. Validate calibration on 3-month hold-out set
4. Retrain hybrid gate using calibrated prob_win values

### Option B: Adjust Strategy Parameters
1. **Reduce TP target:** Try TP = 0.8% - 1.0% to increase hit rate
2. **Increase SL:** Try SL = 1.2% - 1.5% to reduce false stops on noise
3. **Extend max_hold:** Try max_hold = 3-4 days to allow more runroom
4. **Tighten entry filter:** Only trade on days with prob_win > 0.60 (fewer but higher quality)

### Option C: Different Ticker Universe
1. Run hybrid gate with larger ticker universe (currently only 10 tickers: NVDA, AMD, XOM, CVX, META, TSLA, PFE, JNJ, MSFT, AAPL)
2. Consider sector rotation vs. static selection
3. Add more liquid tickers if available in data

### Option D: Separate Win/Loss by Ticker
Analyze which tickers are profitable vs. losing:
- AMD: 8 trades (all lose?) - should be excluded?
- PFE: May have better hit rate?
- Filter based on per-ticker backtest performance

## Files Generated
- `evidence/backtest_hybrid_gate_full/summary.json` - Summary metrics
- `evidence/backtest_hybrid_gate_full/trades.csv` - Detailed trade log
- `backtest_hybrid_gate_full.py` - Script used for backtest

## Conclusion
The hybrid gate (MC + Signal Quality) successfully identified tickers and generated a backtest, but the results are **negative**. The primary issue is **forecast calibration** - the synthetic prob_win model is not predictive of actual trading success.

**Next Steps:**
1. Investigate why forecast is poorly calibrated
2. Either: (a) recalibrate with real data, or (b) use hybrid gate WITHOUT prob_win filter, or (c) adjust TP/SL parameters
3. Re-run backtest with improvements

---
**Generated:** `backtest_hybrid_gate_full_report.md`  
**Backtest Script:** [backtest_hybrid_gate_full.py](backtest_hybrid_gate_full.py)
