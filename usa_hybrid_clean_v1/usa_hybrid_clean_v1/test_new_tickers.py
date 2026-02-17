#!/usr/bin/env python3
"""
Quick test: run December with NEW 5-ticker universe
OLD: AMD, CVX, XOM, JNJ, WMT
NEW: AMD, CVX, XOM, NVDA, MSFT (removed underperformers JNJ, WMT; added tech leaders)
"""

import subprocess
import sys

tickers_old = "AMD,CVX,XOM,JNJ,WMT"
tickers_new = "AMD,CVX,XOM,NVDA,MSFT"

print("=" * 90)
print("TICKER DIVERSIFICATION TEST")
print("=" * 90)

print(f"\nOLD (5 tickers, known underperformers):")
print(f"  Tickers: {tickers_old}")
print(f"  Issue: JNJ lost -$7.42, WMT lost -$8.00 (combined -$15.42)")

print(f"\nNEW (5 tickers, swapped underperformers for top performers):")
print(f"  Tickers: {tickers_new}")
print(f"  Changes:")
print(f"    ❌ Remove: JNJ (22% WR, -$7.42), WMT (42% WR, -$8.00)")
print(f"    ✅ Add: NVDA, MSFT (top Tech S&P500, should improve diversification)")
print(f"  Expected impact:")
print(f"    - Better diversification (Tech + Energy + Semiconductors)")
print(f"    - Remove negative contributors (-$15.42)")
print(f"    - Tech exposure to market leaders")

print(f"\n{'='*90}")
print(f"Running walk-forward with OLD tickers...")
print(f"{'='*90}\n")

cmd_old = [
    "python", "paper/wf_paper_month.py",
    "--month", "2025-12",
    "--tickers", tickers_old,
    "--execution-mode", "balanced",
    "--max-hold-days", "2",
    "--tp-pct", "0.02",
    "--sl-pct", "0.012"
]

print(f"Command: {' '.join(cmd_old)}\n")
result_old = subprocess.run(cmd_old, capture_output=True, text=True)

if "P&L" in result_old.stdout or "Total P&L" in result_old.stdout:
    # Extract P&L from output
    for line in result_old.stdout.split('\n'):
        if 'P&L' in line or 'Total P&L' in line or 'Win Rate' in line or 'Trades' in line:
            print(line)

print(f"\n{'='*90}")
print(f"Running walk-forward with NEW tickers...")
print(f"{'='*90}\n")

cmd_new = [
    "python", "paper/wf_paper_month.py",
    "--month", "2025-12",
    "--tickers", tickers_new,
    "--execution-mode", "balanced",
    "--max-hold-days", "2",
    "--tp-pct", "0.02",
    "--sl-pct", "0.012"
]

print(f"Command: {' '.join(cmd_new)}\n")
result_new = subprocess.run(cmd_new, capture_output=True, text=True)

if "P&L" in result_new.stdout or "Total P&L" in result_new.stdout:
    for line in result_new.stdout.split('\n'):
        if 'P&L' in line or 'Total P&L' in line or 'Win Rate' in line or 'Trades' in line:
            print(line)

print(f"\n{'='*90}")
print(f"SUMMARY")
print(f"{'='*90}")
print(f"OLD tickers P&L vs NEW tickers P&L")
print(f"\nAnalyze the terminal output above for:")
print(f"  - Total P&L difference")
print(f"  - Win Rate improvement")
print(f"  - Number of trades (diversification)")
print(f"\nRecommendation: Use NEW tickers if P&L improves by >$10-20")
print(f"{'='*90}\n")
