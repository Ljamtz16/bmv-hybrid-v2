import pandas as pd

df = pd.read_parquet("data/daily/signals_with_gates.parquet")
print("=== Regime Distribution ===")
print(df["regime"].value_counts(dropna=False))
print(f"\nTotal signals: {len(df)}")
print(f"\nColumns: {sorted(df.columns)}")
print(f"\nSample row:")
print(df[['ticker','regime','prob_win','prob_win_cal']].head(3))
