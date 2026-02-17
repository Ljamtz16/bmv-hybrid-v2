import pandas as pd

# Detectar tickers con splits (ratio cambio >5x en un día)
daily = pd.read_parquet(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\daily_bars.parquet')
daily = daily.sort_values(['ticker', 'date'])

daily['pct_change'] = daily.groupby('ticker')['close'].pct_change().abs()

splits = daily[daily['pct_change'] > 0.5].copy()  # cambio >50% sugiere split/reverse split
print("=== TICKERS CON POSIBLES SPLITS ===")
print(splits[['ticker', 'date', 'close', 'pct_change']].sort_values('pct_change', ascending=False))

split_tickers = splits['ticker'].unique()
print(f"\nTickers a excluir: {list(split_tickers)}")

# Regenerar plan sin estos tickers
plan = pd.read_csv(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan.csv')
print(f"\nPlan original: {len(plan)} trades")

plan_clean = plan[~plan['ticker'].isin(split_tickers)]
print(f"Plan sin splits: {len(plan_clean)} trades")

plan_clean.to_csv(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan_clean.csv', index=False)
print("\n✅ Plan limpio guardado en: intraday_plan_clean.csv")
