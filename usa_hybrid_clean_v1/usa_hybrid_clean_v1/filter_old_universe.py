#!/usr/bin/env python3
import pandas as pd
from pathlib import Path

target = {'AMD','CVX','XOM','JNJ','WMT'}
src = Path('data/daily/signals_with_gates.parquet')
dst = Path('data/daily/signals_with_gates_old5.parquet')
if not src.exists():
    print('missing signals_with_gates.parquet'); raise SystemExit(1)
df = pd.read_parquet(src)
filtered = df[df['ticker'].isin(target)].copy()
filtered.to_parquet(dst, index=False)
print('saved', dst, 'rows', len(filtered), 'tickers', sorted(filtered['ticker'].unique()))
