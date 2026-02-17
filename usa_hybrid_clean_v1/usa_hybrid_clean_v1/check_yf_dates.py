"""
Check what dates are available from yfinance for recent data
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

TICKERS = ['SPY', 'AAPL', 'MSFT', 'QQQ']

print("Checking available dates from yfinance...")
print(f"Today: {datetime.now().strftime('%Y-%m-%d')}\n")

for ticker in TICKERS:
    print(f"{ticker}:")
    # Try downloading last 10 days
    df = yf.download(ticker, period="10d", interval="15m", progress=False)
    if not df.empty:
        print(f"  Data range: {df.index.min()} to {df.index.max()}")
    else:
        print(f"  No data available")
    print()
