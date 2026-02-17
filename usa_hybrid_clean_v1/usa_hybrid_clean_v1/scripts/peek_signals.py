import pandas as pd
import sys
p = sys.argv[1] if len(sys.argv) > 1 else 'data/daily/signals_with_gates.parquet'
df = pd.read_parquet(p)
df_nv = df[df['ticker']=='NVDA'].sort_values('timestamp')
print('Columns:', list(df.columns)[:40])
print(df_nv[['timestamp','open','high','low','close','prob_win_cal']].tail(5).to_string(index=False))
