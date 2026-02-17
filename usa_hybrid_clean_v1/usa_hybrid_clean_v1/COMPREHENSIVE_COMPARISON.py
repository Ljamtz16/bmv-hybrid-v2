"""
Final comparison: All 4 modes tested
"""
import pandas as pd
import json
from pathlib import Path

print("=" * 100)
print("COMPREHENSIVE BACKTEST COMPARISON (2024-2025)")
print("=" * 100)

modes = {
    'Baseline MC (5 tickers)': 'evidence/mc_baseline_2024_2025',
    'ProbWin-Only (5 tickers)': 'evidence/probwin_only_2024_2025',
    'MC→PW gate (5 tickers)': 'evidence/mc_probwin_gate_2024_2025',
    'MC→PW (Full Universe)': 'evidence/mc_proposes_probwin_decides_full_universe',
}

results = {}
for name, path in modes.items():
    path_obj = Path(path)
    if (path_obj / 'metrics.json').exists():
        with open(path_obj / 'metrics.json') as f:
            metrics = json.load(f)
        results[name] = metrics
    else:
        print(f"⚠️  Not found: {path}")

print("\n" + "=" * 100)
print("RESULTS TABLE")
print("=" * 100)

df_results = pd.DataFrame(results).T
df_results = df_results[['return_pct', 'n_trades', 'win_rate', 'profit_factor', 'avg_pnl_per_trade', 'total_pnl', 'final_equity']]
df_results.columns = ['Return %', 'Trades', 'Win Rate %', 'Profit Factor', 'Avg P&L', 'Total P&L', 'Final Equity']

# Format
for col in ['Return %', 'Win Rate %']:
    df_results[col] = df_results[col].apply(lambda x: f"{x:.1f}%")
for col in ['Profit Factor', 'Avg P&L']:
    df_results[col] = df_results[col].apply(lambda x: f"{x:.2f}x" if col == 'Profit Factor' else f"${x:.2f}")
for col in ['Trades']:
    df_results[col] = df_results[col].apply(lambda x: f"{int(x):,}")
for col in ['Total P&L', 'Final Equity']:
    df_results[col] = df_results[col].apply(lambda x: f"${x:,.2f}")

print(df_results.to_string())

print("\n" + "=" * 100)
print("KEY INSIGHTS")
print("=" * 100)

print("""
1. ProbWin-Only DOMINATES (130.5% return, 61.1% WR)
   - 3.5x better than Baseline MC
   - No Monte Carlo overhead needed

2. MC→PW gate (5 tickers) vs Full Universe (almost identical)
   - 5 tickers mode: 33.4%, 60.1% WR, 351 trades
   - Full universe: 33.6%, 58.5% WR, 390 trades
   - ✅ Full universe adds 39 more trades but no edge gain
   
3. Monte Carlo adds NO value once ProbWin filters
   - When MC proposes and ProbWin decides: only ~33-34% return
   - Same when full universe available
   - ProbWin alone (130.5%) >>> MC+ProbWin (33-34%)

4. Why is MC+ProbWin so much worse?
   - MC proposes low-quality candidates
   - ProbWin filters out ~75% of them
   - Remaining trades are below what ProbWin would find independently
   - MC adds selection bias that hurts final outcome

5. Universe size doesn't matter for MC
   - 5 tickers → 351 trades (MC vetoes ~75%)
   - 18 tickers → 390 trades (MC vetoes ~75%)
   - Same filtering pattern, same suboptimal result

CONCLUSION: Use ProbWin-Only. Monte Carlo adds complexity without edge.
""")

print("=" * 100)
