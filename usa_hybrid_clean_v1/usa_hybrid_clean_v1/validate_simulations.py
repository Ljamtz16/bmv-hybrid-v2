#!/usr/bin/env python3
"""Validate intraday simulation results"""

import pandas as pd
import json
from pathlib import Path

print('[VALIDACIÓN DE SIMULACIONES INTRADAY 2022-2025]\n')
print('='*70)

configs = [
    ('TP=1.6%, SL=1%', 'evidence/paper_2022_2025_intraday_600_tp1p6_sl1'),
    ('TP=2.0%, SL=1%', 'evidence/paper_2022_2025_intraday_600_tp2_sl1')
]

results = []

for name, path in configs:
    p = Path(path)
    trades_file = p / 'all_trades.csv'
    summary_file = p / 'summary.json'
    
    if not trades_file.exists():
        print(f'\n{name}: ❌ NO ENCONTRADO')
        continue
    
    df = pd.read_csv(trades_file)
    summary = json.loads(summary_file.read_text()) if summary_file.exists() else {}
    
    total_pnl = summary.get('total_pnl', 0)
    final_equity = summary.get('final_equity', 0)
    win_rate = summary.get('win_rate_pct', 0)
    win_count = summary.get('win_count', 0)
    loss_count = summary.get('loss_count', 0)
    profit_factor = summary.get('profit_factor', 0)
    
    tp_exits = (df['exit_reason'] == 'TP').sum()
    sl_exits = (df['exit_reason'] == 'SL').sum()
    timeout_exits = (df['exit_reason'] == 'TIMEOUT').sum()
    
    print(f'\n✅ {name}:')
    print(f'  📊 Trades: {len(df):,}')
    print(f'  💰 Total P&L: ${total_pnl:,.2f}')
    print(f'  💵 Final Equity: ${final_equity:,.2f}')
    print(f'  📈 ROI: {(final_equity - 600) / 600 * 100:.1f}%')
    print(f'  🎯 Win Rate: {win_rate:.1f}%')
    print(f'  ⚖️  Wins/Losses: {win_count}/{loss_count}')
    
    if profit_factor != float('inf'):
        print(f'  📊 Profit Factor: {profit_factor:.2f}x')
    else:
        print(f'  📊 Profit Factor: ∞')
    
    print(f'  💵 Avg P&L/trade: ${total_pnl / len(df):.2f}')
    print(f'\n  Exit Breakdown:')
    print(f'    ✓ TP:      {tp_exits:,} ({tp_exits / len(df) * 100:.1f}%)')
    print(f'    ✗ SL:      {sl_exits:,} ({sl_exits / len(df) * 100:.1f}%)')
    print(f'    ⏱ TIMEOUT: {timeout_exits:,} ({timeout_exits / len(df) * 100:.1f}%)')
    
    # Date range
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    print(f'\n  📅 Date Range: {df["trade_date"].min().date()} to {df["trade_date"].max().date()}')
    
    # Tickers
    tickers = sorted(df['ticker'].unique())
    print(f'  🎯 Tickers: {len(tickers)} - {", ".join(tickers[:5])}{"..." if len(tickers) > 5 else ""}')
    
    results.append({
        'name': name,
        'trades': len(df),
        'pnl': total_pnl,
        'equity': final_equity,
        'roi': (final_equity - 600) / 600 * 100,
        'win_rate': win_rate,
        'profit_factor': profit_factor
    })

# Comparison
if len(results) == 2:
    print('\n' + '='*70)
    print('\n📊 COMPARACIÓN:')
    r1, r2 = results
    
    print(f'\n  P&L Difference: ${r2["pnl"] - r1["pnl"]:,.2f}')
    print(f'  ROI Difference: {r2["roi"] - r1["roi"]:.1f} pp')
    print(f'  Win Rate Difference: {r2["win_rate"] - r1["win_rate"]:.1f} pp')
    print(f'  Trades Difference: {r2["trades"] - r1["trades"]:,}')
    
    if r2['pnl'] > r1['pnl']:
        print(f'\n  ✅ {r2["name"]} tiene mejor P&L (+${r2["pnl"] - r1["pnl"]:.2f})')
    else:
        print(f'\n  ✅ {r1["name"]} tiene mejor P&L (+${r1["pnl"] - r2["pnl"]:.2f})')

print('\n' + '='*70)
print('\n✅ Validación completa\n')
