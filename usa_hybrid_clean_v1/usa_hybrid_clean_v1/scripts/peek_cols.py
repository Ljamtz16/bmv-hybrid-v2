import pandas as pd
import sys
p = sys.argv[1]
df = pd.read_parquet(p) if p.endswith('.parquet') else pd.read_csv(p)
print('ncols:', len(df.columns))
print('entry_price in columns:', 'entry_price' in df.columns)
print('columns:', list(df.columns))
