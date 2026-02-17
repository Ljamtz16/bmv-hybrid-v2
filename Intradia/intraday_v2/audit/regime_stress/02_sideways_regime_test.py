# Regime Stress Test 2: Pure Sideways Regime
# Define sideways days by ATR percentile, EMA50 slope, and 30d return

import json
from pathlib import Path
import numpy as np
import pandas as pd

DATASET_PATH = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
TRADES_PATH = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
OUTPUT_DIR = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\regime_stress')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _prepare_dataset():
    df = pd.read_parquet(DATASET_PATH)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    return df


def _prepare_trades():
    trades = pd.read_csv(TRADES_PATH)
    trades['entry_dt'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    return trades


def _rolling_percentile(series, window=30):
    return series.rolling(window).apply(lambda x: x.rank(pct=True).iloc[-1], raw=False)


def sideways_regime_test():
    print("[RS-02] === SIDEWAYS REGIME TEST ===\n")

    df = _prepare_dataset()
    trades = _prepare_trades()

    # Use full dataset/trades for regime detection
    if len(df) == 0:
        results = {'error': 'No data available in dataset'}
        with open(OUTPUT_DIR / 'sideways_regime_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("[RS-02] ⚠️ No data available. Results saved with error.")
        return results

    # Compute regime indicators per ticker
    df = df.sort_values(['ticker', 'date'])
    df['ema50'] = df.groupby('ticker')['w_close'].transform(lambda x: x.ewm(span=50, adjust=False).mean())
    df['ema50_slope'] = df.groupby('ticker')['ema50'].transform(lambda x: (x - x.shift(3)) / x.shift(3))
    df['ret_30d'] = df.groupby('ticker')['w_close'].transform(lambda x: x / x.shift(30) - 1.0)
    df['atr_pct'] = df.groupby('ticker')['atr14'].transform(lambda x: _rolling_percentile(x, window=20))

    # Sideways regime rules (relaxed)
    atr_thresh = 0.60
    slope_thresh = 0.003  # 0.3% over ~3 trading days
    ret_low, ret_high = -0.05, 0.05

    sideways = df[
        (df['atr_pct'] < atr_thresh) &
        (df['ema50_slope'].abs() < slope_thresh) &
        (df['ret_30d'].between(ret_low, ret_high))
    ].copy()

    if len(sideways) == 0:
        results = {'error': 'No sideways regime days found with current thresholds'}
        with open(OUTPUT_DIR / 'sideways_regime_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("[RS-02] ⚠️ No sideways regime days. Results saved with error.")
        return results

    # Join with trades by ticker + date to improve coverage
    sideways['entry_date'] = sideways['date'].dt.date
    trades['entry_date'] = trades['entry_dt'].dt.date
    trades_sub = trades[['ticker', 'entry_date', 'r_mult']]
    merged = pd.merge(sideways, trades_sub, on=['ticker', 'entry_date'], how='inner')

    if len(merged) == 0:
        # Fallback: match by date only (market-level sideways day)
        trades_sub = trades[['entry_date', 'r_mult']]
        merged = pd.merge(sideways[['entry_date']], trades_sub, on='entry_date', how='inner')
        if len(merged) == 0:
            results = {'error': 'No trades matched to sideways regime days'}
            with open(OUTPUT_DIR / 'sideways_regime_results.json', 'w') as f:
                json.dump(results, f, indent=2)
            print("[RS-02] ⚠️ No trades matched. Results saved with error.")
            return results
        else:
            print("[RS-02] ⚠️ No ticker match; using date-only match (market-level sideways days)")

    r_vals = merged['r_mult'].values
    wins = r_vals[r_vals > 0]
    losses = r_vals[r_vals <= 0]

    wr = len(wins) / len(r_vals)
    gross_profit = wins.sum() if len(wins) else 0
    gross_loss = abs(losses.sum()) if len(losses) else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else 0

    # Max DD
    equity = 1.0
    peak = equity
    max_dd = 0.0
    for r in r_vals:
        equity *= (1 + r * 0.01)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    if 'entry_dt' in merged.columns:
        trade_days = merged['entry_dt'].dt.date.nunique()
    else:
        trade_days = merged['entry_date'].nunique()
    trade_freq = len(r_vals) / trade_days if trade_days > 0 else 0

    results = {
        'sideways_days': int(len(sideways)),
        'trades': int(len(r_vals)),
        'wr': float(wr),
        'pf': float(pf),
        'mean_r': float(np.mean(r_vals)),
        'max_dd': float(max_dd),
        'trade_freq_per_day': float(trade_freq),
        'thresholds': {
            'atr_pct_lt': atr_thresh,
            'ema50_slope_abs_lt': slope_thresh,
            'ret_30d_between': [ret_low, ret_high]
        }
    }

    with open(OUTPUT_DIR / 'sideways_regime_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("[RS-02] Results saved to sideways_regime_results.json")
    return results


if __name__ == '__main__':
    sideways_regime_test()
