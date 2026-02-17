# Regime Stress Test 4: Regime Segmentation Analysis
# Segment OOS trades by volatility and trend regimes

import pandas as pd
import numpy as np
from pathlib import Path

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


def _metrics(r_vals):
    wins = r_vals[r_vals > 0]
    losses = r_vals[r_vals <= 0]
    wr = len(wins) / len(r_vals) if len(r_vals) else 0
    gross_profit = wins.sum() if len(wins) else 0
    gross_loss = abs(losses.sum()) if len(losses) else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else 0
    return {
        'trades': int(len(r_vals)),
        'wr': float(wr),
        'pf': float(pf),
        'avg_r': float(np.mean(r_vals)),
        'expectancy': float(np.mean(r_vals))
    }


def regime_segmentation_analysis():
    print("[RS-04] === REGIME SEGMENTATION ANALYSIS ===\n")

    df = _prepare_dataset()
    trades = _prepare_trades()

    oos_start = pd.Timestamp('2025-07-01')
    oos_end = pd.Timestamp('2026-02-13')

    df = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)].copy()

    if len(df) == 0:
        out = Path(OUTPUT_DIR / 'regime_segmentation_results.csv')
        pd.DataFrame([{'error': 'No OOS data in 2025-07-01 to 2026-02-13'}]).to_csv(out, index=False)
        print("[RS-04] ⚠️ No OOS data. Results saved with error.")
        return

    # Regime features
    df = df.sort_values(['ticker', 'date'])
    df['ema200'] = df.groupby('ticker')['w_close'].transform(lambda x: x.ewm(span=200, adjust=False).mean())

    atr_hi = df['atr14'].quantile(0.75)
    atr_lo = df['atr14'].quantile(0.25)

    df['regime_vol'] = np.where(df['atr14'] >= atr_hi, 'high_vol', np.where(df['atr14'] <= atr_lo, 'low_vol', 'mid_vol'))
    df['regime_trend'] = np.where(df['w_close'] >= df['ema200'], 'bull', 'bear')

    # Join trades
    df['entry_dt'] = pd.to_datetime(df['date'].dt.strftime('%Y-%m-%d') + ' ' + df['start_time'])
    trades_sub = trades[['ticker', 'entry_dt', 'r_mult']]
    merged = pd.merge(df, trades_sub, on=['ticker', 'entry_dt'], how='inner')

    if len(merged) == 0:
        out = Path(OUTPUT_DIR / 'regime_segmentation_results.csv')
        pd.DataFrame([{'error': 'No trades matched to OOS dataset'}]).to_csv(out, index=False)
        print("[RS-04] ⚠️ No trades matched. Results saved with error.")
        return

    results = []

    # Volatility regimes
    for vol in ['high_vol', 'low_vol']:
        subset = merged[merged['regime_vol'] == vol]
        if len(subset) == 0:
            continue
        m = _metrics(subset['r_mult'].values)
        m.update({'regime': f'vol_{vol}'})
        results.append(m)

    # Trend regimes
    for trend in ['bull', 'bear']:
        subset = merged[merged['regime_trend'] == trend]
        if len(subset) == 0:
            continue
        m = _metrics(subset['r_mult'].values)
        m.update({'regime': f'trend_{trend}'})
        results.append(m)

    pd.DataFrame(results).to_csv(OUTPUT_DIR / 'regime_segmentation_results.csv', index=False)
    print("[RS-04] Results saved to regime_segmentation_results.csv")


if __name__ == '__main__':
    regime_segmentation_analysis()
