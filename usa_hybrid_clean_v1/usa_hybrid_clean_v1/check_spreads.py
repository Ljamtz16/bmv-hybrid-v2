import pandas as pd

df = pd.read_parquet('features/intraday/2025-10-27.parquet')
print('Spread stats (bps):')
print(df['spread_bps'].describe())
print(f'\nP10-P90: {df["spread_bps"].quantile(0.1):.1f} - {df["spread_bps"].quantile(0.9):.1f}')
print(f'\nMin-Max: {df["spread_bps"].min():.1f} - {df["spread_bps"].max():.1f}')
