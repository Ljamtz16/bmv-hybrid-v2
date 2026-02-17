#!/usr/bin/env python3
"""
Download 15m intraday data for S&P 500 tickers (top 100)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

# Top 100 S&P 500 tickers by market cap
SP500_TICKERS = [
    # Tech
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'GOOG', 'META', 'TSLA', 'AVGO', 'ASML', 'ARM',
    # Finance
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'SCHW', 'SPGI', 'ICE', 'CME',
    # Healthcare
    'JNJ', 'UNH', 'MRK', 'AZN', 'PFE', 'ABBV', 'LLY', 'CVS', 'CI', 'HCA',
    # Energy
    'XOM', 'CVX', 'MPC', 'PSX', 'COP', 'EOG', 'OXY', 'SLB', 'HAL', 'MUR',
    # Industrial
    'BA', 'CAT', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'GD', 'MMM', 'ABB',
    # Consumer
    'WMT', 'KO', 'MCD', 'PG', 'CL', 'KMB', 'PEP', 'MO', 'PM', 'COST',
    # Retail
    'AMZN', 'HD', 'NKE', 'TJX', 'ULTA', 'ADYEY', 'RCL', 'MAR', 'LVS', 'MGM',
    # Communication
    'VZ', 'T', 'CMCSA', 'DIS', 'FOX', 'FOXA', 'PARA', 'CHTR', 'REGN', 'VRTX',
    # Utilities/Real Estate
    'NEE', 'DUK', 'SO', 'AEP', 'EXC', 'WEC', 'PEG', 'EVRG', 'PPL', 'AMT',
    # Materials
    'NEM', 'FCX', 'SCCO', 'AA', 'NUCOR', 'CLF', 'ALB', 'GEVO', 'ARCH', 'CF',
]

# Remove duplicates and sort
SP500_TICKERS = sorted(list(set(SP500_TICKERS)))

print(f"Downloading 15m data for {len(SP500_TICKERS)} S&P 500 tickers...")
print(f"Tickers: {SP500_TICKERS}\n")

def download_month(month_str, tickers):
    """
    Download 15m data for a month
    month_str: "2025-12" or "2026-01"
    """
    year, month = month_str.split('-')
    year = int(year)
    month = int(month)
    
    # Start date: first trading day of month
    start_date = datetime(year, month, 1)
    
    # End date: last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print(f"\n{'='*100}")
    print(f"Downloading {month_str}: {start_str} to {end_str}")
    print(f"{'='*100}")
    
    all_data = []
    success_count = 0
    
    for i, ticker in enumerate(tickers):
        try:
            print(f"[{i+1}/{len(tickers)}] {ticker}...", end=" ", flush=True)
            
            data = yf.download(
                ticker,
                start=start_str,
                end=end_str,
                interval='15m',
                progress=False,
                prepost=False
            )
            
            if data.empty:
                print("❌ NO DATA")
                continue
            
            data['ticker'] = ticker
            data = data.reset_index()
            
            print(f"✅ {len(data)} rows")
            all_data.append(data)
            success_count += 1
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)[:50]}")
            continue
    
    if all_data:
        df = pd.concat(all_data, ignore_index=True)
        
        # Save to parquet
        output_dir = 'data/intraday_15m_sp500'
        os.makedirs(output_dir, exist_ok=True)
        output_file = f'{output_dir}/{month_str}.parquet'
        
        df.to_parquet(output_file)
        
        print(f"\n{'='*100}")
        print(f"✅ Downloaded {success_count} tickers, {len(df)} total rows")
        print(f"   Saved to: {output_file}")
        print(f"{'='*100}\n")
        
        return output_file
    else:
        print(f"❌ No data downloaded for {month_str}")
        return None

# Download both months
print(f"\n{'='*100}")
print("S&P 500 15m DATA DOWNLOAD - EXPANDED UNIVERSE")
print(f"{'='*100}\n")

output_files = []

# December 2025
output_files.append(download_month('2025-12', SP500_TICKERS))

# January 2026
output_files.append(download_month('2026-01', SP500_TICKERS))

print(f"\n{'='*100}")
print("DOWNLOAD COMPLETE")
print(f"{'='*100}")
for f in output_files:
    if f:
        print(f"✅ {f}")

print(f"\nNext: Modify forecast to rank all {len(SP500_TICKERS)} tickers daily")
print(f"Then: Run walk-forward with expanded universe\n")
