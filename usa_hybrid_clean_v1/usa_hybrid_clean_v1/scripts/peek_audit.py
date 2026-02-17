import pandas as pd
sym=['NVDA','AMD','MS','XOM','CVX','CAT','TSLA','JPM']
df=pd.read_parquet('val/trade_plan_audit.parquet')
d=df[df['ticker'].isin(sym)].sort_values(['ticker','timestamp'])
print(d.groupby('ticker')[['timestamp','close','entry_price']].tail(1).to_string())
