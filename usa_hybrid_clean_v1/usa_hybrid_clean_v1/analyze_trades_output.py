#!/usr/bin/env python3
import pandas as pd
from pathlib import Path

path = Path('evidence/paper_sep_2025/all_trades.csv')
if not path.exists():
    print('missing all_trades.csv')
    raise SystemExit(1)

df = pd.read_csv(path)
print('tickers:', sorted(df['ticker'].unique()))
print('\ncounts:\n', df['ticker'].value_counts())
print('\npnl by ticker:\n', df.groupby('ticker')['pnl'].sum().sort_values())
