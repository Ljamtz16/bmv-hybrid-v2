"""
Análisis: ¿Qué veta ProbWin cuando MC propone?
"""
import pandas as pd
import numpy as np
from pathlib import Path

# Load results
mc_only = pd.read_csv('evidence/mc_baseline_2024_2025/trades.csv')
probwin_only = pd.read_csv('evidence/probwin_only_2024_2025/trades.csv')
mc_gate = pd.read_csv('evidence/mc_probwin_gate_2024_2025/trades.csv')

print("=" * 80)
print("COMPARATIVE ANALYSIS: MC vs ProbWin")
print("=" * 80)

print("\n### 1. TRADE COUNTS ###")
print(f"Baseline MC:       {len(mc_only):4d} trades")
print(f"ProbWin-Only:      {len(probwin_only):4d} trades")
print(f"MC→ProbWin gate:   {len(mc_gate):4d} trades")
print(f"\nReduction (MC→gate vs MC):     {1 - len(mc_gate) / len(mc_only):.1%}")
print(f"Reduction (MC→gate vs PWO):   {1 - len(mc_gate) / len(probwin_only):.1%}")

print("\n### 2. QUALITY COMPARISON ###")
for name, df in [('Baseline MC', mc_only), ('ProbWin-Only', probwin_only), ('MC→ProbWin', mc_gate)]:
    wr = (df['pnl'] > 0).mean()
    avg_pnl = df['pnl'].mean()
    pf = df[df['pnl'] > 0]['pnl'].sum() / abs(df[df['pnl'] < 0]['pnl'].sum()) if len(df[df['pnl'] < 0]) > 0 else 999
    print(f"\n{name:20s}:")
    print(f"  WR: {wr:.1%} | AvgPnL: ${avg_pnl:+.2f} | PF: {pf:.2f}x")

print("\n### 3. MC→GATE INTERSECTION ANALYSIS ###")
# Which tickers are in MC but NOT in gate?
mc_tickers = set(mc_only['ticker'].unique())
gate_tickers = set(mc_gate['ticker'].unique())
filtered_out_tickers = mc_tickers - gate_tickers

print(f"\nTickers in MC:         {sorted(mc_tickers)}")
print(f"Tickers in MC→gate:    {sorted(gate_tickers)}")
print(f"Tickers FILTERED OUT:  {sorted(filtered_out_tickers)}")

# Performance on filtered-out tickers
if filtered_out_tickers:
    filtered_trades = mc_only[mc_only['ticker'].isin(filtered_out_tickers)]
    print(f"\nTrades REMOVED by prob_win filter: {len(filtered_trades)}")
    print(f"  WR: {(filtered_trades['pnl'] > 0).mean():.1%}")
    print(f"  AvgPnL: ${filtered_trades['pnl'].mean():+.2f}")
    print(f"  Median P&L: ${filtered_trades['pnl'].median():+.2f}")

print("\n### 4. PER-TICKER BREAKDOWN (WHAT'S HAPPENING?) ###")
for ticker in sorted(mc_tickers):
    mc_trades = len(mc_only[mc_only['ticker'] == ticker])
    gate_trades = len(mc_gate[mc_gate['ticker'] == ticker])
    pw_trades = len(probwin_only[probwin_only['ticker'] == ticker])
    
    mc_wr = (mc_only[mc_only['ticker'] == ticker]['pnl'] > 0).mean()
    gate_wr = (mc_gate[mc_gate['ticker'] == ticker]['pnl'] > 0).mean() if gate_trades > 0 else np.nan
    pw_wr = (probwin_only[probwin_only['ticker'] == ticker]['pnl'] > 0).mean()
    
    filtered = mc_trades - gate_trades
    filter_pct = filtered / mc_trades if mc_trades > 0 else 0
    
    print(f"\n{ticker}:")
    print(f"  MC only:    {mc_trades:3d} trades (WR {mc_wr:.1%})")
    print(f"  MC→gate:    {gate_trades:3d} trades (WR {gate_wr:.1%}) - Filtered {filtered:3d} ({filter_pct:.0%})")
    print(f"  ProbWin-O:  {pw_trades:3d} trades (WR {pw_wr:.1%})")

print("\n### 5. INTERPRETATION ###")
print("\nScenario Check:")
if len(mc_gate) < len(probwin_only):
    print("  🟡 MC is BLOCKING too much ← ProbWin veto too aggressive")
    print("  → MC should either:")
    print("     a) Propose BETTER candidates (different scoring)")
    print("     b) Be REMOVED entirely (it adds no edge)")

elif len(mc_gate) > len(probwin_only):
    print("  🟢 MC ADDS value ← Proposes candidates ProbWin would miss")
    
else:
    print("  🟡 Neutral ← MC proposes same as ProbWin would find")

print("\n" + "=" * 80)
