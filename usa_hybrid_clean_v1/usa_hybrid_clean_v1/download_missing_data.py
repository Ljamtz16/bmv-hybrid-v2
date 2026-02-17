"""
Download missing intraday data from yfinance (21-23 Jan 2026)
and append to existing consolidated_15m.parquet
"""
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Configuration
DATA_FILE = Path("C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")
TICKERS = ['AAPL', 'AMD', 'AMZN', 'CAT', 'CVX', 'GS', 'IWM', 'JNJ', 'JPM', 'MS', 'MSFT', 'NVDA', 'PFE', 'QQQ', 'SPY', 'TSLA', 'WMT', 'XOM']
START_DATE = "2026-01-21"
END_DATE = "2026-01-23"

print("="*80)
print("DOWNLOADING MISSING INTRADAY DATA FROM YFINANCE")
print("="*80)
print(f"\nTickers: {len(TICKERS)}")
print(f"Period: {START_DATE} to {END_DATE}")
print(f"Interval: 15 minutes")

# Load existing data
print(f"\n[1/4] Loading existing data...")
existing_df = pd.read_parquet(DATA_FILE)
existing_cols = existing_df.columns.tolist()
last_date = existing_df['timestamp'].max()
print(f"  Existing data: {len(existing_df):,} rows")
print(f"  Last date: {last_date}")
print(f"  Columns: {existing_cols}")

# Download new data
print(f"\n[2/4] Downloading from yfinance...")
new_data = []

for ticker in TICKERS:
    print(f"  {ticker}...", end=" ", flush=True)
    try:
        # Download 15-min data
        df = yf.download(
            ticker, 
            start=START_DATE, 
            end=END_DATE, 
            interval="15m",
            progress=False
        )
        
        if not df.empty:
            df = df.reset_index()
            df['ticker'] = ticker
            
            # Handle column names properly
            df.columns = [str(c).lower() for c in df.columns]
            
            # Rename datetime column
            if 'datetime' in df.columns:
                df = df.rename(columns={'datetime': 'timestamp'})
            elif 'date' in df.columns:
                df = df.rename(columns={'date': 'timestamp'})
            
            # Select needed columns
            cols_needed = ['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
            cols_available = [c for c in cols_needed if c in df.columns]
            df = df[cols_available]
            
            new_data.append(df)
            print(f"✓ {len(df)} bars")
        else:
            print("(no data)")
    except Exception as e:
        print(f"✗ {str(e)[:50]}")

# Combine data
print(f"\n[3/4] Combining data...")
if new_data:
    new_df = pd.concat(new_data, ignore_index=True)
    print(f"  New data before dedup: {len(new_df):,} rows")
    new_df = new_df.drop_duplicates(subset=['ticker', 'timestamp'], keep='last')
    print(f"  New data after dedup: {len(new_df):,} rows")
    
    # Combine with existing - remove duplicates from new data vs existing
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['ticker', 'timestamp'], keep='last')
    combined = combined.sort_values(['timestamp', 'ticker'])
    
    print(f"  Combined: {len(combined):,} rows")
    
    # Save
    print(f"\n[4/4] Saving...")
    combined.to_parquet(DATA_FILE, index=False)
    print(f"  ✓ Saved to {DATA_FILE}")
    
    # Summary
    print(f"\n" + "="*80)
    print(f"NEW DATA SUMMARY")
    print(f"="*80)
    print(f"Date range: {combined['timestamp'].min()} to {combined['timestamp'].max()}")
    print(f"Total rows: {len(combined):,}")
    print(f"Tickers: {combined['ticker'].nunique()}")
    print(f"\nRows added: {len(combined) - len(existing_df):,}")
else:
    print("  No new data found!")

print(f"\n✓ DONE")
