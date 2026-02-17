#!/usr/bin/env python3
"""
Compare FAST vs BALANCED execution modes for December 2025
"""

import pandas as pd

print("=" * 80)
print("DECEMBER 2025 - FAST vs BALANCED COMPARISON")
print("=" * 80)

# Load both datasets
df_balanced = pd.read_csv('evidence/paper_dec_2025_15m_FIXED/all_trades.csv')
df_fast = pd.read_csv('evidence/paper_dec_2025_15m_FAST/all_trades.csv')

print("\n" + "=" * 80)
print("PORTFOLIO METRICS")
print("=" * 80)
print(f"{'Metric':<30} {'BALANCED':<20} {'FAST':<20} {'Difference'}")
print("-" * 80)

metrics = {
    'Total Trades': (len(df_balanced), len(df_fast)),
    'Total P&L': (df_balanced['pnl'].sum(), df_fast['pnl'].sum()),
    'Win Rate': (len(df_balanced[df_balanced['pnl'] > 0]) / len(df_balanced) * 100, 
                 len(df_fast[df_fast['pnl'] > 0]) / len(df_fast) * 100),
    'Avg P&L per trade': (df_balanced['pnl'].mean(), df_fast['pnl'].mean()),
    'Trades per day': (len(df_balanced) / 21, len(df_fast) / 21),
}

for metric, (bal, fast) in metrics.items():
    if 'P&L' in metric:
        diff = fast - bal
        print(f"{metric:<30} ${bal:>8.2f}          ${fast:>8.2f}          ${diff:>+8.2f}")
    elif 'Rate' in metric:
        diff = fast - bal
        print(f"{metric:<30} {bal:>7.1f}%           {fast:>7.1f}%           {diff:>+7.1f}%")
    elif 'per' in metric:
        diff = fast - bal
        print(f"{metric:<30} {bal:>8.2f}           {fast:>8.2f}           {diff:>+8.2f}")
    else:
        diff = fast - bal
        print(f"{metric:<30} {bal:>8.0f}            {fast:>8.0f}            {diff:>+8.0f}")

print("\n" + "=" * 80)
print("EXIT REASONS")
print("=" * 80)
print(f"\nBALANCED (80 trades):")
print(df_balanced['exit_reason'].value_counts())
print(f"\nFAST (21 trades):")
print(df_fast['exit_reason'].value_counts())

print("\n" + "=" * 80)
print("PROFITABILITY BREAKDOWN")
print("=" * 80)

# Winners
bal_winners = df_balanced[df_balanced['pnl'] > 0]
fast_winners = df_fast[df_fast['pnl'] > 0]

print(f"\n{'Metric':<30} {'BALANCED':<20} {'FAST':<20}")
print("-" * 70)
print(f"{'Winners:':<30} {len(bal_winners):<20} {len(fast_winners):<20}")
print(f"{'Avg Winner P&L:':<30} ${bal_winners['pnl'].mean():<19.2f} ${fast_winners['pnl'].mean():<19.2f}")
print(f"{'Total Winner P&L:':<30} ${bal_winners['pnl'].sum():<19.2f} ${fast_winners['pnl'].sum():<19.2f}")

# Losers
bal_losers = df_balanced[df_balanced['pnl'] < 0]
fast_losers = df_fast[df_fast['pnl'] < 0]

print(f"\n{'Losers:':<30} {len(bal_losers):<20} {len(fast_losers):<20}")
print(f"{'Avg Loser P&L:':<30} ${bal_losers['pnl'].mean():<19.2f} ${fast_losers['pnl'].mean():<19.2f}")
print(f"{'Total Loser P&L:':<30} ${bal_losers['pnl'].sum():<19.2f} ${fast_losers['pnl'].sum():<19.2f}")

print("\n" + "=" * 80)
print("RISK METRICS")
print("=" * 80)

print(f"\n{'Metric':<30} {'BALANCED':<20} {'FAST':<20}")
print("-" * 70)

# MFE/MAE
print(f"{'Avg MFE (best profit):':<30} {df_balanced['mfe_pct'].mean()*100:<19.2f}% {df_fast['mfe_pct'].mean()*100:<19.2f}%")
print(f"{'Avg MAE (worst loss):':<30} {df_balanced['mae_pct'].mean()*100:<19.2f}% {df_fast['mae_pct'].mean()*100:<19.2f}%")
print(f"{'Avg TP distance:':<30} {df_balanced['tp_distance_pct'].mean()*100:<19.2f}% {df_fast['tp_distance_pct'].mean()*100:<19.2f}%")
print(f"{'Avg SL distance:':<30} {df_balanced['sl_distance_pct'].mean()*100:<19.2f}% {df_fast['sl_distance_pct'].mean()*100:<19.2f}%")

# Hold time
print(f"\n{'Avg hold hours:':<30} {df_balanced['hold_hours'].mean():<19.1f} {df_fast['hold_hours'].mean():<19.1f}")
print(f"{'Avg hold days:':<30} {df_balanced['hold_hours'].mean()/24:<19.1f} {df_fast['hold_hours'].mean()/24:<19.1f}")

print("\n" + "=" * 80)
print("TICKERS TRADED")
print("=" * 80)

print(f"\nBALANCED ticker distribution:")
print(df_balanced['ticker'].value_counts())

print(f"\nFAST ticker distribution:")
print(df_fast['ticker'].value_counts())

print("\n" + "=" * 80)
print("CONCLUSIONS")
print("=" * 80)

pnl_diff = df_fast['pnl'].sum() - df_balanced['pnl'].sum()
wr_diff = (len(df_fast[df_fast['pnl'] > 0]) / len(df_fast) - len(df_balanced[df_balanced['pnl'] > 0]) / len(df_balanced)) * 100

print(f"\n🎯 FAST mode trades {len(df_fast)}/{len(df_balanced)} = {len(df_fast)/len(df_balanced)*100:.1f}% of BALANCED trades")
print(f"   - Concentrated: {21/21:.1f} trade/day vs {80/21:.1f} trades/day (BALANCED)")

if pnl_diff < 0:
    print(f"\n📉 FAST underperformed by ${abs(pnl_diff):.2f} ({abs(pnl_diff/df_balanced['pnl'].sum()*100):.1f}x worse)")
    print(f"   - FAST: ${df_fast['pnl'].sum():.2f} loss")
    print(f"   - BALANCED: ${df_balanced['pnl'].sum():.2f} loss")
else:
    print(f"\n📈 FAST outperformed by ${pnl_diff:.2f}")

if wr_diff < 0:
    print(f"\n⚠️  FAST win rate {abs(wr_diff):.1f}% LOWER ({len(df_fast[df_fast['pnl'] > 0]) / len(df_fast) * 100:.1f}% vs {len(df_balanced[df_balanced['pnl'] > 0]) / len(df_balanced) * 100:.1f}%)")
else:
    print(f"\n✅ FAST win rate {wr_diff:.1f}% HIGHER")

# SL rate
bal_sl_rate = len(df_balanced[df_balanced['exit_reason'] == 'SL']) / len(df_balanced) * 100
fast_sl_rate = len(df_fast[df_fast['exit_reason'] == 'SL']) / len(df_fast) * 100

print(f"\n🔴 Stop loss hit rate:")
print(f"   - BALANCED: {bal_sl_rate:.1f}% ({len(df_balanced[df_balanced['exit_reason'] == 'SL'])}/{len(df_balanced)})")
print(f"   - FAST: {fast_sl_rate:.1f}% ({len(df_fast[df_fast['exit_reason'] == 'SL'])}/{len(df_fast)})")

if fast_sl_rate > bal_sl_rate:
    print(f"   ⚠️  FAST hits SL {fast_sl_rate - bal_sl_rate:.1f}% MORE often")
else:
    print(f"   ✅ FAST hits SL {bal_sl_rate - fast_sl_rate:.1f}% LESS often")

print("\n" + "=" * 80)
print("RECOMMENDATION")
print("=" * 80)

if df_fast['pnl'].sum() > df_balanced['pnl'].sum() and fast_sl_rate < bal_sl_rate:
    print("\n✅ FAST mode is BETTER for this period:")
    print("   - Higher P&L with fewer trades")
    print("   - Lower stop loss rate")
    print("   - Better trade selection")
elif df_balanced['pnl'].sum() > df_fast['pnl'].sum():
    print("\n✅ BALANCED mode is BETTER for this period:")
    print("   - Higher total P&L through diversification")
    print("   - More trades = more opportunities")
    print("   - Lower concentration risk")
else:
    print("\n⚖️  BOTH modes performed similarly:")
    print("   - Use BALANCED for diversification")
    print("   - Use FAST for concentration on best signals")

print("\n" + "=" * 80)
