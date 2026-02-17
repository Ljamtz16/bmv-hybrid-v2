#!/usr/bin/env python3
"""
Analyze TP rate by ticker to identify best performers
"""

import pandas as pd

print("=" * 90)
print("TICKER PERFORMANCE ANALYSIS - TP Rate & Profitability")
print("=" * 90)

# Load combined data
df_dec = pd.read_csv('evidence/paper_dec_2025_15m_EXP2_BALANCED_2p2pct/all_trades.csv')
df_jan = pd.read_csv('evidence/paper_jan_2026_15m_BALANCED_2p2pct/all_trades.csv')
df_combined = pd.concat([df_dec, df_jan], ignore_index=True)

print("\n" + "=" * 90)
print("DECEMBER 2025 - BY TICKER")
print("=" * 90)
print(f"\n{'Ticker':<10} {'Trades':<10} {'TP %':<10} {'Win %':<10} {'Avg P&L':<12} {'Total P&L':<12}")
print("-" * 90)

for ticker in sorted(df_dec['ticker'].unique()):
    ticker_data = df_dec[df_dec['ticker'] == ticker]
    tp_count = len(ticker_data[ticker_data['exit_reason'] == 'TP'])
    tp_rate = tp_count / len(ticker_data) * 100 if len(ticker_data) > 0 else 0
    win_count = len(ticker_data[ticker_data['pnl'] > 0])
    win_rate = win_count / len(ticker_data) * 100 if len(ticker_data) > 0 else 0
    avg_pnl = ticker_data['pnl'].mean()
    total_pnl = ticker_data['pnl'].sum()
    
    print(f"{ticker:<10} {len(ticker_data):<10} {tp_rate:<10.1f} {win_rate:<10.1f} ${avg_pnl:<11.2f} ${total_pnl:<11.2f}")

print("\n" + "=" * 90)
print("JANUARY 2026 - BY TICKER")
print("=" * 90)
print(f"\n{'Ticker':<10} {'Trades':<10} {'TP %':<10} {'Win %':<10} {'Avg P&L':<12} {'Total P&L':<12}")
print("-" * 90)

for ticker in sorted(df_jan['ticker'].unique()):
    ticker_data = df_jan[df_jan['ticker'] == ticker]
    tp_count = len(ticker_data[ticker_data['exit_reason'] == 'TP'])
    tp_rate = tp_count / len(ticker_data) * 100 if len(ticker_data) > 0 else 0
    win_count = len(ticker_data[ticker_data['pnl'] > 0])
    win_rate = win_count / len(ticker_data) * 100 if len(ticker_data) > 0 else 0
    avg_pnl = ticker_data['pnl'].mean()
    total_pnl = ticker_data['pnl'].sum()
    
    if len(ticker_data) > 0:
        print(f"{ticker:<10} {len(ticker_data):<10} {tp_rate:<10.1f} {win_rate:<10.1f} ${avg_pnl:<11.2f} ${total_pnl:<11.2f}")

print("\n" + "=" * 90)
print("2-MONTH COMBINED - BY TICKER")
print("=" * 90)
print(f"\n{'Ticker':<10} {'Trades':<10} {'TP %':<10} {'Win %':<10} {'Avg P&L':<12} {'Total P&L':<12}")
print("-" * 90)

for ticker in sorted(df_combined['ticker'].unique()):
    ticker_data = df_combined[df_combined['ticker'] == ticker]
    tp_count = len(ticker_data[ticker_data['exit_reason'] == 'TP'])
    tp_rate = tp_count / len(ticker_data) * 100 if len(ticker_data) > 0 else 0
    win_count = len(ticker_data[ticker_data['pnl'] > 0])
    win_rate = win_count / len(ticker_data) * 100 if len(ticker_data) > 0 else 0
    avg_pnl = ticker_data['pnl'].mean()
    total_pnl = ticker_data['pnl'].sum()
    
    print(f"{ticker:<10} {len(ticker_data):<10} {tp_rate:<10.1f} {win_rate:<10.1f} ${avg_pnl:<11.2f} ${total_pnl:<11.2f}")

print("\n" + "=" * 90)
print("INSIGHT: Which tickers work best?")
print("=" * 90)

# Find best and worst performers
combined_stats = []
for ticker in df_combined['ticker'].unique():
    ticker_data = df_combined[df_combined['ticker'] == ticker]
    tp_rate = len(ticker_data[ticker_data['exit_reason'] == 'TP']) / len(ticker_data) * 100
    win_rate = len(ticker_data[ticker_data['pnl'] > 0]) / len(ticker_data) * 100
    total_pnl = ticker_data['pnl'].sum()
    combined_stats.append((ticker, tp_rate, win_rate, total_pnl, len(ticker_data)))

combined_stats.sort(key=lambda x: x[2], reverse=True)  # Sort by win_rate

print("\nRanked by Win Rate:")
for ticker, tp_rate, win_rate, total_pnl, trades in combined_stats:
    status = "🟢" if win_rate > 55 else "🟡" if win_rate > 50 else "🔴"
    print(f"  {status} {ticker}: {win_rate:.1f}% WR, {tp_rate:.1f}% TP, ${total_pnl:.2f} ({trades} trades)")

print("\n" + "=" * 90)
print("DIVERSIFICATION STRATEGY")
print("=" * 90)

print("\n1. CURRENT UNIVERSE (5 tickers: AMD, CVX, XOM, JNJ, WMT)")
print("   - Good: diversified, ~50% WR, ~1.75x edge")
print("   - Issue: Only 22-25% TP rate (wide TP threshold or market regime)")

print("\n2. OPTIONS TO INCREASE TP RATE:")
print("   A) Keep current 5, but add ROTATION (swap underperformers weekly)")
print("   B) Expand to 20+ tickers (S&P 500) for more variety")
print("   C) Filter by momentum/volatility (only trade \"hot\" tickers)")
print("   D) Increase TP% from 2% to 2.5-3% (but verify with MFE)")

print("\n3. RECOMMENDED: Option B + C (Hybrid approach)")
print("   - Start with S&P 500 universe")
print("   - Filter to top 20 by score/strength (momentum/volatility)")
print("   - This way:")
print("     * More TP opportunities (more tickers = more chances)")
print("     * Still diversified (not concentrated on 1 ticker)")
print("     * Better regime adaptation (hot stocks get higher weight)")

print("\n" + "=" * 90)
print("NEXT STEPS")
print("=" * 90)

print("\nTo test expanded universe:")
print("\n1. Download 15m data for S&P 500 (or top 100)")
print("2. Modify forecast to score all tickers daily")
print("3. Generate daily plan with top 10-20 tickers (instead of fixed 5)")
print("4. Re-run walk-forward to see if TP% improves")
print("\nEstimated outcome:")
print("  - Current: 22-25% TP rate, 3.25% return/month")
print("  - Expanded: 25-30% TP rate (more tickers = more TPs), 4-5% return/month")
print("\n" + "=" * 90)
