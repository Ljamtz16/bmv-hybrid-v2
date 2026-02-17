import pandas as pd
from pathlib import Path
import sys

src = sys.argv[1] if len(sys.argv) > 1 else 'data/daily/features_daily_enhanced.parquet'
col_date = 'timestamp'

if src.endswith('.parquet'):
    df = pd.read_parquet(src)
else:
    df = pd.read_csv(src)
    if 'date' in df.columns:
        df['timestamp'] = pd.to_datetime(df['date'], utc=True)
        col_date = 'timestamp'

symbols = ['NVDA','AMD','MS','WMT','PFE','XOM','TSLA','JPM','CVX','CAT']
sub = df[df['ticker'].isin(symbols)].copy()
sub = sub.sort_values([ 'ticker', col_date ])
last = sub.groupby('ticker').tail(1)
cols = [c for c in ['ticker', col_date, 'open','high','low','close'] if c in last.columns]
print(last[cols].to_string(index=False))
