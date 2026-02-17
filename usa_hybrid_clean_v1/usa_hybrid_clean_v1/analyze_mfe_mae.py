#!/usr/bin/env python3
"""
Analyze MFE/MAE metrics from December 2025 fixed run
"""

import pandas as pd

df = pd.read_csv('evidence/paper_dec_2025_15m_FIXED/all_trades.csv')

print("=" * 80)
print("DECEMBER 2025 - FIXED ENTRY PRICE")
print("=" * 80)

print(f"\nTotal trades: {len(df)}")
print(f"\nExit reasons:")
print(df["exit_reason"].value_counts())

print("\n" + "=" * 80)
print("MFE (Max Favorable Excursion) - Best unrealized profit")
print("=" * 80)
print(df['mfe_pct'].describe())

print("\n" + "=" * 80)
print("MAE (Max Adverse Excursion) - Worst unrealized loss")
print("=" * 80)
print(df['mae_pct'].describe())

print("\n" + "=" * 80)
print("TP CALIBRATION ANALYSIS")
print("=" * 80)
print(f"Avg TP distance (target):     {df['tp_distance_pct'].mean():.4f} ({df['tp_distance_pct'].mean()*100:.2f}%)")
print(f"Avg MFE reached (actual):     {df['mfe_pct'].mean():.4f} ({df['mfe_pct'].mean()*100:.2f}%)")
print(f"\nTrades where MFE >= TP:       {(df['mfe_pct'] >= df['tp_distance_pct']).sum()} / {len(df)} ({(df['mfe_pct'] >= df['tp_distance_pct']).sum()/len(df)*100:.1f}%)")
print(f"  → TP was REACHABLE but not hit (likely timeout before TP)")

print("\n" + "=" * 80)
print("SL CALIBRATION ANALYSIS")
print("=" * 80)
print(f"Avg SL distance (risk):       {df['sl_distance_pct'].mean():.4f} ({df['sl_distance_pct'].mean()*100:.2f}%)")
print(f"Avg MAE reached (actual):     {df['mae_pct'].mean():.4f} ({df['mae_pct'].mean()*100:.2f}%)")
print(f"\nTrades where MAE <= -SL:      {(df['mae_pct'] <= -df['sl_distance_pct']).sum()} / {len(df)} ({(df['mae_pct'] <= -df['sl_distance_pct']).sum()/len(df)*100:.1f}%)")
print(f"  → SL was HIT correctly")

print("\n" + "=" * 80)
print("EFFICIENCY METRICS")
print("=" * 80)

# Profitable trades
profitable = df[df['pnl'] > 0]
losing = df[df['pnl'] < 0]

print(f"\nProfitable trades: {len(profitable)} ({len(profitable)/len(df)*100:.1f}%)")
if len(profitable) > 0:
    print(f"  Avg profit: ${profitable['pnl'].mean():.2f}")
    print(f"  Avg MFE: {profitable['mfe_pct'].mean()*100:.2f}%")
    print(f"  Avg hold: {profitable['hold_hours'].mean():.1f} hours")

print(f"\nLosing trades: {len(losing)} ({len(losing)/len(df)*100:.1f}%)")
if len(losing) > 0:
    print(f"  Avg loss: ${losing['pnl'].mean():.2f}")
    print(f"  Avg MAE: {losing['mae_pct'].mean()*100:.2f}%")
    print(f"  Avg hold: {losing['hold_hours'].mean():.1f} hours")

# Timeout analysis
timeouts = df[df['exit_reason'] == 'TIMEOUT']
print(f"\nTimeouts: {len(timeouts)} ({len(timeouts)/len(df)*100:.1f}%)")
if len(timeouts) > 0:
    print(f"  Avg PnL: ${timeouts['pnl'].mean():.2f}")
    print(f"  Avg MFE: {timeouts['mfe_pct'].mean()*100:.2f}%")
    print(f"  Avg MAE: {timeouts['mae_pct'].mean()*100:.2f}%")
    print(f"  Profitable timeouts: {len(timeouts[timeouts['pnl'] > 0])} / {len(timeouts)}")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

mfe_tp_ratio = df['mfe_pct'].mean() / df['tp_distance_pct'].mean()
print(f"\nMFE/TP ratio: {mfe_tp_ratio:.2f}")
if mfe_tp_ratio < 0.5:
    print("  ⚠️  TP TOO AMBITIOUS - Price rarely reaches even 50% of target")
elif mfe_tp_ratio < 0.8:
    print("  ⚠️  TP MODERATELY AMBITIOUS - Consider reducing TP distance by 20-30%")
else:
    print("  ✅ TP REASONABLE - Price frequently reaches near target")

mae_sl_ratio = abs(df['mae_pct'].mean()) / df['sl_distance_pct'].mean()
print(f"\nMAE/SL ratio: {mae_sl_ratio:.2f}")
if mae_sl_ratio > 1.2:
    print("  ⚠️  SL TOO TIGHT - Frequent stop-outs, consider widening SL by 20-30%")
elif mae_sl_ratio > 0.8:
    print("  ⚠️  SL MODERATELY TIGHT - Some improvement possible")
else:
    print("  ✅ SL REASONABLE - Adequate risk buffer")

print("\n" + "=" * 80)
