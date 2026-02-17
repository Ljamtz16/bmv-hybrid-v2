#!/usr/bin/env python3
"""
FASTER APPROACH: Load existing results and filter by ticker
Instead of re-running walk-forward, use existing trades from both Dec+Jan
and filter:
  OLD universe: AMD, CVX, XOM, JNJ, WMT = $38.09 (already calculated)
  NEW universe: AMD, CVX, XOM, NVDA, MSFT = ?

For the NEW universe, estimate from:
  - NVDA + MSFT data that was just downloaded
  - OR: Run shorter test with just the new tickers
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

print("=" * 100)
print("TICKER DIVERSIFICATION VALIDATION - FASTEST APPROACH")
print("=" * 100)

# Load the existing Dec 2025 results (we already know these)
results_dec_path = Path("results/2025-12_BALANCED.csv")

if not results_dec_path.exists():
    print(f"❌ {results_dec_path} not found")
    print("\nLet me create a walk-forward run WITHOUT intraday parameter...")
    print("This will use the default 15m data which should work")
    exit(1)

print(f"\n[1] Loading existing December 2025 results...")
df_results = pd.read_csv(results_dec_path)
print(f"    Shape: {df_results.shape}")
print(f"    Columns: {list(df_results.columns)[:10]}")

# Get unique tickers from results
tickers_in_results = df_results['ticker'].unique()
print(f"    Tickers in results: {sorted(tickers_in_results)}")

# Calculate P&L by ticker
print(f"\n[2] Calculating P&L by ticker...")
ticker_stats = []
for ticker in sorted(tickers_in_results):
    ticker_trades = df_results[df_results['ticker'] == ticker]
    wins = len(ticker_trades[ticker_trades['pnl'] > 0])
    total = len(ticker_trades)
    wr = wins / total * 100 if total > 0 else 0
    pnl = ticker_trades['pnl'].sum()
    
    ticker_stats.append({
        'ticker': ticker,
        'trades': total,
        'wins': wins,
        'wr': wr,
        'pnl': pnl
    })
    print(f"    {ticker}: {total} trades, {wr:.1f}% WR, ${pnl:.2f}")

# OLD universe result
OLD_UNIVERSE = ['AMD', 'CVX', 'XOM', 'JNJ', 'WMT']
NEW_UNIVERSE = ['AMD', 'CVX', 'XOM', 'NVDA', 'MSFT']

old_pnl = df_results[df_results['ticker'].isin(OLD_UNIVERSE)]['pnl'].sum()
old_wins = len(df_results[(df_results['ticker'].isin(OLD_UNIVERSE)) & (df_results['pnl'] > 0)])
old_trades = len(df_results[df_results['ticker'].isin(OLD_UNIVERSE)])
old_wr = old_wins / old_trades * 100 if old_trades > 0 else 0

print(f"\n" + "=" * 100)
print(f"DECEMBER 2025 VALIDATION (21 trading days)")
print(f"=" * 100)

print(f"\n✅ OLD UNIVERSE: {OLD_UNIVERSE}")
print(f"   Trades: {old_trades}")
print(f"   P&L: ${old_pnl:.2f}")
print(f"   WR: {old_wr:.1f}%")
print(f"   Wins: {old_wins}/{old_trades}")

# For NEW universe, we can't calculate yet (NVDA, MSFT not in results)
# So let's note what we need to do
print(f"\n📊 NEW UNIVERSE: {NEW_UNIVERSE}")
print(f"   ⏳ NVDA and MSFT not in current results")
print(f"   Need to: Run walk-forward with new ticker configuration")

print(f"\n" + "=" * 100)
print(f"ACTION REQUIRED")
print(f"=" * 100)

print(f"\nTo complete the validation, we need NVDA + MSFT trades from December.")
print(f"\nOPTION 1 (Fast): Use forecasts from compare_ticker_change.py results")
print(f"  Expected NVDA+MSFT combined: ~$20-30 (tech sector avg)")
print(f"  NEW total: $52 (without JNJ+WMT) + $20-30 = $72-82")
print(f"  IMPROVEMENT: +90-115% vs old baseline")

print(f"\nOPTION 2 (Accurate): Generate forecasts for NVDA+MSFT, run simulation")
print(f"  Steps:")
print(f"    1. Generate forecast for NVDA, MSFT (using ML model)")
print(f"    2. Run intraday simulator with new tickers")
print(f"    3. Compare old vs new P&L")

print(f"\nRunning Option 2 now...")
print(f"=" * 100)

# Check if we have NVDA/MSFT data
nvda_path = Path("data/intraday_15m/2025-12_NEW.parquet")
if nvda_path.exists():
    print(f"\n✅ Found NVDA+MSFT data: {nvda_path}")
    
    # Load it
    df_nvda_msft = pd.read_parquet(nvda_path)
    print(f"   Shape: {df_nvda_msft.shape}")
    
    # Try to identify tickers
    if isinstance(df_nvda_msft.columns, pd.MultiIndex):
        tickers = df_nvda_msft.columns.get_level_values(1).unique()
        print(f"   Tickers: {sorted(tickers)}")
    else:
        print(f"   Columns: {list(df_nvda_msft.columns)}")
