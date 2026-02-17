import pandas as pd

# Check NVDA 2024-06-21
bars = pd.read_parquet(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet')
daily = pd.read_parquet(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\daily_bars.parquet')

# Intraday
nvda_bars = bars[bars['ticker'] == 'NVDA'].copy()
nvda_bars['date'] = pd.to_datetime(nvda_bars['timestamp']).dt.date
target_date = pd.Timestamp('2024-06-21').date()
sample = nvda_bars[nvda_bars['date'] == target_date]

print("=== NVDA 2024-06-21 INTRADAY ===")
print(f"Samples: {len(sample)}")
if len(sample) > 0:
    print(f"Range: {sample['low'].min():.2f} - {sample['high'].max():.2f}")
    print("\nFirst 5 bars:")
    print(sample[['timestamp', 'open', 'high', 'low', 'close']].head())

# Daily
nvda_daily = daily[daily['ticker'] == 'NVDA'].copy()
nvda_daily['date'] = pd.to_datetime(nvda_daily['date']).dt.date
daily_sample = nvda_daily[nvda_daily['date'] == target_date]

print("\n=== NVDA 2024-06-21 DAILY ===")
if len(daily_sample) > 0:
    print(daily_sample[['date', 'open', 'high', 'low', 'close']])
else:
    print("No data")

# Check around split date
print("\n=== NVDA around 2024-06-10 (split date) ===")
nvda_daily_range = nvda_daily[(nvda_daily['date'] >= pd.Timestamp('2024-06-05').date()) & 
                               (nvda_daily['date'] <= pd.Timestamp('2024-06-25').date())]
print(nvda_daily_range[['date', 'open', 'high', 'low', 'close']])
