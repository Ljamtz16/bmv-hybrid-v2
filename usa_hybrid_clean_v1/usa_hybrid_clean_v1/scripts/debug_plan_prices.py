import pandas as pd

sig = pd.read_parquet('data/daily/signals_with_gates.parquet')
plan = pd.read_csv('val/trade_plan.csv')

sel = plan[['ticker','entry_price']].copy()
last_sig = sig.sort_values('timestamp').groupby('ticker').tail(1)[['ticker','timestamp','close']]
merged = sel.merge(last_sig, on='ticker', how='left')
merged['diff_pct'] = (merged['entry_price'] - merged['close'])/merged['close']
print(merged.to_string(index=False))
