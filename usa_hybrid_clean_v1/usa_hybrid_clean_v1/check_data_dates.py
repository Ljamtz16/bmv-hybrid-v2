import pandas as pd

df = pd.read_parquet('C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet')

print("="*80)
print("DATOS INTRADAY (15-min)")
print("="*80)
print(f"\nFecha inicial: {df['timestamp'].min()}")
print(f"Fecha final:   {df['timestamp'].max()}")
print(f"Total barras:  {len(df):,}")
print(f"Tickers:       {sorted(df['ticker'].unique())}")

# Stats por ticker
print(f"\n{'Ticker':<10} {'Barras':<15} {'Fecha primera':<20} {'Fecha última':<20}")
print("-"*65)
for ticker in sorted(df['ticker'].unique()):
    ticker_df = df[df['ticker'] == ticker]
    print(f"{ticker:<10} {len(ticker_df):<15,} {str(ticker_df['timestamp'].min()):<20} {str(ticker_df['timestamp'].max()):<20}")
