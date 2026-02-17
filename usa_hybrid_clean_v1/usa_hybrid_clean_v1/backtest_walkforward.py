"""
Walk-forward backtest by semester
Tests robustness of ProbWin-Only strategy across time periods
"""

import subprocess
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ==============================================================================
# CONFIGURATION
# ==============================================================================
PERIODS = [
    {
        'name': '2024_H1',
        'start': '2024-01-01',
        'end': '2024-06-30',
        'description': '2024 First Half (Jan-Jun)'
    },
    {
        'name': '2024_H2',
        'start': '2024-07-01',
        'end': '2024-12-31',
        'description': '2024 Second Half (Jul-Dec)'
    },
    {
        'name': '2025_H1',
        'start': '2025-01-01',
        'end': '2025-06-30',
        'description': '2025 First Half (Jan-Jun)'
    },
    {
        'name': '2025_H2',
        'start': '2025-07-01',
        'end': '2025-12-31',
        'description': '2025 Second Half (Jul-Dec)'
    }
]

OUTPUT_BASE = Path("evidence/walkforward_analysis")
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# RUN WALK-FORWARD TESTS
# ==============================================================================
print("=" * 90)
print("WALK-FORWARD ROBUSTNESS TEST: ProbWin-Only by Semester")
print("=" * 90)

results = []

for period in PERIODS:
    print(f"\n{'=' * 90}")
    print(f"Testing: {period['description']}")
    print(f"Period: {period['start']} to {period['end']}")
    print(f"{'=' * 90}\n")
    
    output_dir = OUTPUT_BASE / period['name']
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create temporary backtest script with period-specific START/END dates
    cmd = [
        'python', '-c', rf"""
import pandas as pd
import json
import numpy as np
import sys
sys.path.insert(0, '.')

# Override dates
START_DATE = '{period['start']}'
END_DATE = '{period['end']}'

from backtest_comparative_modes import (
    load_data, run_backtest, analyze_results, ensure_trade_schema
)

# Load data for this period
intraday_df, daily_df, forecast_df = load_data(
    'probwin_only', 
    'evidence/forecast_retrained_robust/forecast_prob_win_retrained.parquet'
)

# Manually override date range (hacky but works for walk-forward)
import datetime as dt
start_dt = pd.to_datetime('{period['start']}')
end_dt = pd.to_datetime('{period['end']}')
intraday_df = intraday_df[
    (intraday_df['date'] >= start_dt) & 
    (intraday_df['date'] <= end_dt)
].copy()
daily_df = daily_df[
    (daily_df['date'] >= start_dt) & 
    (daily_df['date'] <= end_dt)
].copy()
if forecast_df is not None:
    forecast_df = forecast_df[
        (forecast_df['date'] >= start_dt) & 
        (forecast_df['date'] <= end_dt)
    ].copy()

print(f"Filtered to {{len(intraday_df)}} intraday bars")
print(f"Filtered to {{len(daily_df)}} daily bars")

# Run backtest
trades_df, final_equity, equity_curve = run_backtest(
    'probwin_only', intraday_df, daily_df, forecast_df,
    pw_threshold=0.55
)

# Ensure schema
trades_df = ensure_trade_schema(trades_df)

# Analyze
metrics = analyze_results(trades_df, final_equity, 'probwin_only_{period['name']}')

# Save
import pathlib
output_dir = pathlib.Path('{output_dir}')
output_dir.mkdir(parents=True, exist_ok=True)
trades_df.to_csv(output_dir / 'trades.csv', index=False)
with open(output_dir / 'metrics.json', 'w') as f:
    json.dump(metrics, f, indent=2)
print(f"Saved to {{output_dir}}")
"""
    ]
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode == 0:
        metrics_file = output_dir / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file) as f:
                metrics = json.load(f)
            metrics['period'] = period['name']
            metrics['description'] = period['description']
            results.append(metrics)
            print(f"\n[OK] {period['name']} completed")

# ==============================================================================
# AGGREGATE RESULTS
# ==============================================================================
print("\n" + "=" * 90)
print("WALK-FORWARD SUMMARY")
print("=" * 90)

# Discover all walkforward metrics files
from pathlib import Path as PathLib
base_path = PathLib("evidence")
metrics_files = sorted(base_path.glob("walkforward_analysis*/metrics.json"))

results = []
for metrics_file in metrics_files:
    try:
        with open(metrics_file, 'r', encoding='utf-8') as f:
            metrics = json.load(f)
        metrics['run_dir'] = str(metrics_file.parent)
        results.append(metrics)
    except Exception as e:
        print(f"[WARN] Could not read {metrics_file}: {e}")

if results:
    summary_df = pd.DataFrame([
        {
            'Period': r.get('period', r.get('run_dir', 'Unknown')).replace('evidence/walkforward_analysis', '').replace('\\', ''),
            'Return': f"{r['return_pct']:.1f}%",
            'P&L': f"${r['total_pnl']:.0f}",
            'Trades': r['n_trades'],
            'WR': f"{r['win_rate']:.1%}",
            'PF': f"{r['profit_factor']:.2f}x",
            'AvgPnL': f"${r['avg_pnl_per_trade']:.2f}"
        }
        for r in results
    ])
    
    print(summary_df.to_string(index=False))
    
    # Save summary
    summary_df.to_csv(OUTPUT_BASE / "walkforward_summary.csv", index=False)
    
    # Statistics
    returns = [r['return_pct'] for r in results]
    pnls = [r['total_pnl'] for r in results]
    wrs = [r['win_rate'] for r in results]
    
    print("\n" + "=" * 90)
    print("ROBUSTNESS METRICS")
    print("=" * 90)
    print(f"\nReturn Statistics:")
    print(f"  Mean: {np.mean(returns):.1f}%")
    print(f"  Std Dev: {np.std(returns):.1f}%")
    print(f"  Min: {np.min(returns):.1f}%")
    print(f"  Max: {np.max(returns):.1f}%")
    print(f"  Range: {np.max(returns) - np.min(returns):.1f}% pts")
    
    print(f"\nWin Rate Statistics:")
    print(f"  Mean: {np.mean(wrs):.1%}")
    print(f"  Std Dev: {np.std(wrs):.1%}")
    print(f"  Min: {np.min(wrs):.1%}")
    print(f"  Max: {np.max(wrs):.1%}")
    
    print(f"\nTotal P&L (all periods): ${np.sum(pnls):.0f}")
    
    # Key insight
    print("\n" + "=" * 90)
    print("INTERPRETATION")
    print("=" * 90)
    
    if np.std(returns) < 30:
        print(f"\n[OK] ROBUST: Return std dev {np.std(returns):.1f}% is LOW")
        print(f"  Strategy works consistently across time periods")
    else:
        print(f"\n⚠ VARIABLE: Return std dev {np.std(returns):.1f}% is HIGH")
        print(f"  Performance is period-dependent (risk factor)")
    
    if np.min(returns) > 20:
        print(f"\n[OK] SAFE: Minimum return {np.min(returns):.1f}% is positive in all periods")
    else:
        print(f"\n⚠ DOWNSIDE: Minimum return {np.min(returns):.1f}% in worst period")

    print("\n[SUCCESS] Walk-forward analysis complete")
    print(f"Results saved to: {OUTPUT_BASE}")

else:
    print("\n⚠ No results to analyze!")
