#!/usr/bin/env python3
"""
paper/intraday_data.py
Download and cache intraday OHLC data using yfinance.
"""

import argparse
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime


def download_intraday(tickers, start, end, interval="1h"):
    """Download intraday data for multiple tickers using yfinance."""
    dfs = []
    for ticker in tickers:
        try:
            print(f"[{ticker}] Downloading {interval} data from {start} to {end}...")
            df = yf.download(ticker, start=start, end=end, interval=interval, progress=False)
            if df.empty:
                print(f"[WARN] {ticker}: No data returned")
                continue
            df.reset_index(inplace=True)
            df["ticker"] = ticker
            dfs.append(df)
            print(f"[OK] {ticker}: {len(df)} rows")
        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")
    
    if not dfs:
        raise ValueError("No data retrieved for any ticker")
    
    combined = pd.concat(dfs, ignore_index=True)
    
    # Normalize columns
    if "Date" in combined.columns:
        combined.rename(columns={"Date": "datetime"}, inplace=True)
    elif "Datetime" in combined.columns:
        combined.rename(columns={"Datetime": "datetime"}, inplace=True)
    
    # Ensure datetime is consistent
    combined["datetime"] = pd.to_datetime(combined["datetime"])
    
    # Rename OHLCV columns
    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    combined.rename(columns=rename_map, inplace=True)
    
    # Select relevant columns
    cols = ["datetime", "ticker", "open", "high", "low", "close", "volume"]
    combined = combined[cols].copy()
    
    # Sort
    combined = combined.sort_values(["ticker", "datetime"]).reset_index(drop=True)
    
    return combined


def main():
    ap = argparse.ArgumentParser(description="Download and cache intraday OHLC data")
    ap.add_argument("--tickers", nargs="+", required=True, help="List of tickers")
    ap.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    ap.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    ap.add_argument("--interval", default="1h", help="Interval (1m, 1h, 1d)")
    ap.add_argument("--out", required=True, help="Output parquet path")
    
    args = ap.parse_args()
    
    # Download
    df = download_intraday(args.tickers, args.start, args.end, args.interval)
    
    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Total rows: {len(df)}")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    for ticker in args.tickers:
        count = len(df[df["ticker"] == ticker])
        print(f"  {ticker}: {count} rows")
    
    # Save
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out)
    print(f"\n[OK] Saved to {args.out}")


if __name__ == "__main__":
    main()
