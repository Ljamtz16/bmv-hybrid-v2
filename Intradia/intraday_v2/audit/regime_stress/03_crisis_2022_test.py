# Regime Stress Test 3: Crisis 2022 Simulation
# Includes slippage +1 and +2 ticks

import json
from pathlib import Path
import numpy as np
import pandas as pd

TRADES_PATH = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
OUTPUT_DIR = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\regime_stress')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TICK_SIZE = 0.01


def _prepare_trades():
    trades = pd.read_csv(TRADES_PATH)
    trades['entry_dt'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    return trades


def _metrics_from_r(r_vals):
    wins = r_vals[r_vals > 0]
    losses = r_vals[r_vals <= 0]

    wr = len(wins) / len(r_vals) if len(r_vals) else 0
    gross_profit = wins.sum() if len(wins) else 0
    gross_loss = abs(losses.sum()) if len(losses) else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else 0

    equity = 1.0
    peak = equity
    max_dd = 0.0
    for r in r_vals:
        equity *= (1 + r * 0.01)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        'wr': float(wr),
        'pf': float(pf),
        'mean_r': float(np.mean(r_vals)),
        'max_dd': float(max_dd),
        'equity_final': float(equity)
    }


def crisis_2022_test():
    print("[RS-03] === CRISIS 2022 TEST ===\n")

    trades = _prepare_trades()
    start = pd.Timestamp('2022-01-01')
    end = pd.Timestamp('2022-12-31')

    trades_2022 = trades[(trades['entry_dt'] >= start) & (trades['entry_dt'] <= end)].copy()

    if len(trades_2022) == 0:
        results = {'error': 'No trades in 2022 window'}
        with open(OUTPUT_DIR / 'crisis_2022_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("[RS-03] ⚠️ No 2022 trades. Results saved with error.")
        return results

    # Base R
    base_r = trades_2022['r_mult'].values

    # Slippage scenarios
    def apply_slippage(r_vals, entry_price, sl_price, ticks):
        risk = (entry_price - sl_price).values
        adj = (ticks * TICK_SIZE) / risk
        return r_vals - adj

    results = {
        'window': {'start': str(start.date()), 'end': str(end.date())},
        'base': None,
        'slippage_1': None,
        'slippage_2': None,
        'monthly_pf': None,
        'worst_month': None
    }

    # Base
    results['base'] = _metrics_from_r(base_r)

    # Slippage +1, +2 ticks
    r_slip1 = apply_slippage(base_r, trades_2022['entry_price'], trades_2022['sl_price'], 1)
    r_slip2 = apply_slippage(base_r, trades_2022['entry_price'], trades_2022['sl_price'], 2)

    results['slippage_1'] = _metrics_from_r(r_slip1)
    results['slippage_2'] = _metrics_from_r(r_slip2)

    # Monthly PF
    trades_2022['month'] = trades_2022['entry_dt'].dt.to_period('M')
    monthly = []
    for m, g in trades_2022.groupby('month'):
        r_vals = g['r_mult'].values
        metrics = _metrics_from_r(r_vals)
        monthly.append({'month': str(m), 'pf': metrics['pf'], 'wr': metrics['wr'], 'mean_r': metrics['mean_r']})

    results['monthly_pf'] = monthly
    if monthly:
        worst = min(monthly, key=lambda x: x['pf'])
        results['worst_month'] = worst

    with open(OUTPUT_DIR / 'crisis_2022_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("[RS-03] Results saved to crisis_2022_results.json")
    return results


if __name__ == '__main__':
    crisis_2022_test()
