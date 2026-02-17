#!/usr/bin/env python3
import pandas as pd
from pathlib import Path
p=Path('data/daily/features_daily_enhanced.parquet')
if not p.exists():
    print('missing features file'); raise SystemExit(1)
df=pd.read_parquet(p, columns=['ticker'])
print('rows', len(df))
print('unique', df['ticker'].nunique())
print('tickers', sorted(df['ticker'].astype(str).str.upper().unique()))
