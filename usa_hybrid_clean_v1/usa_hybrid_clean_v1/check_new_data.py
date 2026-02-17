import pandas as pd
from datetime import datetime

# Load the updated parquet
df = pd.read_parquet("C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")

# Check latest data
latest = df.sort_values('timestamp').tail(20)
print("Latest 20 rows:")
print(latest[['timestamp', 'ticker', 'close']].to_string())

print(f"\nDate range: {df['timestamp'].min()} to {df['timestamp'].max()}")

# Check if we have any data from Jan 21-23
df['date'] = pd.to_datetime(df['timestamp']).dt.date
jan_dates = df[df['date'] >= datetime(2026, 1, 21).date()]
print(f"\nRows from Jan 21+: {len(jan_dates)}")
if len(jan_dates) > 0:
    print(jan_dates[['timestamp', 'ticker']].head(10).to_string())
