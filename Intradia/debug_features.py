import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression

trades = pd.read_csv('intraday_v2/artifacts/baseline_v1/trades.csv')
trades['entry_time'] = pd.to_datetime(trades['entry_time'], utc=True)
trades['entry_time'] = trades['entry_time'].dt.tz_convert('America/New_York')
trades['month'] = trades['entry_time'].dt.to_period('M').astype(str)
trades['hour_bucket'] = trades['entry_time'].dt.strftime('%H:%M')

trades = trades[trades['exit_reason'].isin(['TP', 'SL', 'EOD'])].copy()
trades = trades[trades['allowed'] == True].copy()

numeric_cols = ['ret1_prev', 'ret4_prev', 'vol4', 'vol_z20', 'atr_ratio', 'body_pct']

df = trades[['ticker', 'entry_time', 'hour_bucket', 'y'] + numeric_cols].copy()
df['y'] = (df['exit_reason'] == 'TP').astype(int) if 'exit_reason' in df.columns else 0

print("Columns before get_dummies:", df.columns.tolist())
print("Data types before:")
print(df.dtypes)

df['ticker_raw'] = df['ticker']
df['hour_bucket_raw'] = df['hour_bucket']

df = pd.get_dummies(df, columns=['ticker', 'hour_bucket'], prefix=['ticker', 'hour'], dummy_na=False)

print("\nColumns after get_dummies:", df.columns.tolist())
print("Data types after:")
print(df.dtypes)

feature_cols = numeric_cols + [c for c in df.columns if c.startswith('ticker_') or c.startswith('hour_')]
print("\nFeature cols:", feature_cols)
print("Feature cols dtypes:", df[feature_cols].dtypes)
