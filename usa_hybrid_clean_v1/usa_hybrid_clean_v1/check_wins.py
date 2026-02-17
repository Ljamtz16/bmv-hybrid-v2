import pandas as pd
from pathlib import Path

files = list(Path('features/intraday').glob('2025-*.parquet'))
dfs = [pd.read_parquet(f) for f in files]
df = pd.concat(dfs, ignore_index=True)

print(f"Total samples: {len(df)}")
print(f"Wins: {df['win'].sum()} ({df['win'].mean():.2%})")
print(f"\nHit types:")
print(df['hit_type'].value_counts())
print(f"\nDirection:")
print(df['direction'].value_counts())
