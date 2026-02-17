#!/usr/bin/env python3
import pandas as pd
from pathlib import Path

path = Path('evidence/paper_jan_2026/all_trades.csv')
if not path.exists():
    print('missing all_trades.csv')
    raise SystemExit(1)

df = pd.read_csv(path)
print('=== JANUARY 2026 RESULTS ===')
print(f'\nTotal trades: {len(df)}')
print(f'Tickers: {sorted(df["ticker"].unique())}')
print(f'\nTrades by ticker:')
print(df['ticker'].value_counts())
print(f'\nP&L by ticker:')
print(df.groupby('ticker')['pnl'].sum().sort_values(ascending=False))
print(f'\nWin rate by ticker:')
for ticker in sorted(df['ticker'].unique()):
    ticker_df = df[df['ticker'] == ticker]
    wins = len(ticker_df[ticker_df['pnl'] > 0])
    wr = wins / len(ticker_df) * 100 if len(ticker_df) > 0 else 0
    print(f'{ticker}: {wr:.1f}% ({wins}/{len(ticker_df)})')
