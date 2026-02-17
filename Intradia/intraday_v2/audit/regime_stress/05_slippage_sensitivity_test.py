# Regime Stress Test 5: Slippage Sensitivity
# Simulate 0/1/2/3 ticks slippage and compute PF/WR/Equity/Max DD

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


def _metrics(r_vals):
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
        'equity_final': float(equity),
        'max_dd': float(max_dd),
        'mean_r': float(np.mean(r_vals))
    }


def _apply_slippage(r_vals, entry_price, sl_price, ticks):
    risk = (entry_price - sl_price).values
    adj = (ticks * TICK_SIZE) / risk
    return r_vals - adj


def slippage_sensitivity_test():
    print("[RS-05] === SLIPPAGE SENSITIVITY TEST ===\n")

    trades = _prepare_trades()
    oos_start = pd.Timestamp('2025-07-01')
    oos_end = pd.Timestamp('2026-02-13')
    trades_oos = trades[(trades['entry_dt'] >= oos_start) & (trades['entry_dt'] <= oos_end)].copy()

    if len(trades_oos) == 0:
        results = {'error': 'No OOS trades in 2025-07-01 to 2026-02-13'}
        with open(OUTPUT_DIR / 'slippage_sensitivity.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("[RS-05] ⚠️ No OOS trades. Results saved with error.")
        return results

    base_r = trades_oos['r_mult'].values

    scenarios = [0, 1, 2, 3]
    results = {'window': {'start': str(oos_start.date()), 'end': str(oos_end.date())}, 'scenarios': []}

    for ticks in scenarios:
        if ticks == 0:
            r_adj = base_r
        else:
            r_adj = _apply_slippage(base_r, trades_oos['entry_price'], trades_oos['sl_price'], ticks)

        metrics = _metrics(r_adj)
        metrics['ticks'] = ticks
        results['scenarios'].append(metrics)

    # PF decay curve data
    results['pf_decay_curve'] = [{'ticks': s['ticks'], 'pf': s['pf']} for s in results['scenarios']]

    with open(OUTPUT_DIR / 'slippage_sensitivity.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("[RS-05] Results saved to slippage_sensitivity.json")
    return results


def generate_report():
    # Optional: aggregate results into a report if all files exist
    report_path = OUTPUT_DIR / 'REGIME_STRESS_REPORT.md'
    required = [
        OUTPUT_DIR / 'extended_period_results.json',
        OUTPUT_DIR / 'sideways_regime_results.json',
        OUTPUT_DIR / 'crisis_2022_results.json',
        OUTPUT_DIR / 'regime_segmentation_results.csv',
        OUTPUT_DIR / 'slippage_sensitivity.json'
    ]

    if not all(p.exists() for p in required):
        return False

    with open(OUTPUT_DIR / 'extended_period_results.json') as f:
        extended = json.load(f)
    with open(OUTPUT_DIR / 'sideways_regime_results.json') as f:
        sideways = json.load(f)
    with open(OUTPUT_DIR / 'crisis_2022_results.json') as f:
        crisis = json.load(f)
    with open(OUTPUT_DIR / 'slippage_sensitivity.json') as f:
        slip = json.load(f)
    regime_df = pd.read_csv(OUTPUT_DIR / 'regime_segmentation_results.csv')

    report = """# Regime Stress Report

## 1. Pre-2020 Performance (Extended 2015–2020)
"""

    report += f"\nFrozen model: {extended.get('frozen_model', {})}\n"
    report += f"\nRefit model: {extended.get('refit_model', {})}\n"

    report += """
## 2. Sideways Regime Robustness
"""
    report += f"\n{sideways}\n"

    report += """
## 3. Crisis 2022 Resilience
"""
    report += f"\nBase: {crisis.get('base', {})}\n"
    report += f"\nSlippage +1: {crisis.get('slippage_1', {})}\n"
    report += f"\nSlippage +2: {crisis.get('slippage_2', {})}\n"
    report += f"\nWorst Month: {crisis.get('worst_month', {})}\n"

    report += """
## 4. Regime Dependency
"""
    report += regime_df.to_string(index=False)

    report += """

## 5. Slippage Tolerance
"""
    report += f"\n{slip}\n"

    report += """

## 6. Final Institutional Verdict

Review the five tests above. If PF or WR collapses in sideways/crisis regimes, the system is regime-dependent.
"""

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    return True


if __name__ == '__main__':
    slippage_sensitivity_test()
    generate_report()
