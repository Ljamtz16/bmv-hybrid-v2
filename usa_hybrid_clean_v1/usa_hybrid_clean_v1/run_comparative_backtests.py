"""
Execute all 3 backtests and compare results
"""

import subprocess
import json
import pandas as pd
from pathlib import Path

# ==============================================================================
# CONFIGURATION
# ==============================================================================
RUNS = [
    {
        'name': 'A_Baseline_PureMC',
        'mode': 'baseline',
        'args': [],
        'description': 'Pure Monte Carlo (5 tickers control)'
    },
    {
        'name': 'B_Hybrid_Bands',
        'mode': 'hybrid',
        'args': ['--pw_bands', '0.52,0.58'],
        'description': 'MC + prob_win sizing bands (0.52-0.58) on 5-ticker forecast universe'
    },
    {
        'name': 'C_ProbWin_Only',
        'mode': 'probwin_only',
        'args': ['--pw_threshold', '0.55'],
        'description': 'Prob_win-only signals (≥0.55, on 5-ticker universe)'
    }
]

OUTPUT_BASE = Path("evidence/comparative_backtests")
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# EXECUTE RUNS
# ==============================================================================
print("=" * 80)
print("EXECUTING COMPARATIVE BACKTESTS")
print("=" * 80)

results = []

for run in RUNS:
    print(f"\n{'=' * 80}")
    print(f"Running: {run['name']}")
    print(f"Description: {run['description']}")
    print(f"{'=' * 80}\n")
    
    output_dir = OUTPUT_BASE / run['name']
    
    cmd = [
        'python',
        'backtest_comparative_modes.py',
        '--mode', run['mode'],
        '--output', str(output_dir)
    ] + run['args']
    
    print(f"Command: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode != 0:
        print(f"⚠️  WARNING: {run['name']} failed with code {result.returncode}")
        continue
    
    # Load metrics
    metrics_file = output_dir / "metrics.json"
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics = json.load(f)
        metrics['name'] = run['name']
        metrics['description'] = run['description']
        results.append(metrics)
        print(f"✅ Completed: {run['name']}")
    else:
        print(f"⚠️  Metrics file not found for {run['name']}")

# ==============================================================================
# COMPARISON TABLE
# ==============================================================================
print("\n" + "=" * 80)
print("📊 COMPARATIVE RESULTS")
print("=" * 80)

if len(results) > 0:
    df = pd.DataFrame(results)
    
    # Reorder columns
    cols = ['name', 'return_pct', 'final_equity', 'n_trades', 'win_rate', 
            'profit_factor', 'avg_pnl_per_trade']
    df = df[cols]
    
    print("\n" + df.to_string(index=False))
    
    # Save comparison
    comparison_file = OUTPUT_BASE / "comparison_summary.csv"
    df.to_csv(comparison_file, index=False)
    print(f"\n✅ Saved comparison to {comparison_file}")
    
    # Highlight best
    print("\n" + "=" * 80)
    print("🏆 BEST PERFORMERS")
    print("=" * 80)
    
    best_return = df.loc[df['return_pct'].idxmax()]
    print(f"\nBest Return: {best_return['name']}")
    print(f"  Return: {best_return['return_pct']:.2f}%")
    print(f"  Trades: {best_return['n_trades']}")
    print(f"  WR: {best_return['win_rate']:.1%}")
    
    best_pf = df.loc[df['profit_factor'].idxmax()]
    print(f"\nBest Profit Factor: {best_pf['name']}")
    print(f"  PF: {best_pf['profit_factor']:.2f}x")
    print(f"  Return: {best_pf['return_pct']:.2f}%")
    
    best_wr = df.loc[df['win_rate'].idxmax()]
    print(f"\nBest Win Rate: {best_wr['name']}")
    print(f"  WR: {best_wr['win_rate']:.1%}")
    print(f"  Return: {best_wr['return_pct']:.2f}%")
    
    # Key insights
    print("\n" + "=" * 80)
    print("💡 KEY INSIGHTS")
    print("=" * 80)
    
    baseline = df[df['name'].str.contains('Baseline')].iloc[0] if len(df[df['name'].str.contains('Baseline')]) > 0 else None
    
    if baseline is not None:
        print(f"\nBaseline (Pure MC): {baseline['return_pct']:.2f}% return on {baseline['n_trades']} trades")
        
        for _, row in df.iterrows():
            if 'Baseline' not in row['name']:
                delta_return = row['return_pct'] - baseline['return_pct']
                delta_trades = row['n_trades'] - baseline['n_trades']
                print(f"\n{row['name']}:")
                print(f"  Return delta: {delta_return:+.2f}% ({row['return_pct']:.2f}% vs {baseline['return_pct']:.2f}%)")
                print(f"  Trades delta: {delta_trades:+d} ({row['n_trades']} vs {baseline['n_trades']})")
                print(f"  WR: {row['win_rate']:.1%} vs {baseline['win_rate']:.1%}")
                print(f"  PF: {row['profit_factor']:.2f}x vs {baseline['profit_factor']:.2f}x")
    
    print("\n" + "=" * 80)
    print("✅ COMPARISON COMPLETE")
    print("=" * 80)
    print(f"\nAll results saved to: {OUTPUT_BASE}")
    print("\nNext steps:")
    print("  1. Review per-ticker performance in trades.csv for each run")
    print("  2. Check prob_win calibration (predicted vs actual WR)")
    print("  3. Analyze drawdowns and equity curves")
    print("  4. If hybrid improves metrics → deploy, else stick to baseline")

else:
    print("\n⚠️  No results to compare!")
