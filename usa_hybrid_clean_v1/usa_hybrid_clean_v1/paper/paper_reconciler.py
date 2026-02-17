#!/usr/bin/env python3
"""
paper/paper_reconciler.py
Update broker mark-to-market with fresh prices.
"""

import argparse
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime
from paper_broker import mark_to_market, load_state


def get_latest_prices_yfinance(tickers, interval="1m"):
    """Fetch latest prices from yfinance."""
    price_map = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="1d", interval=interval, progress=False)
            if not df.empty:
                price_map[ticker] = float(df["Close"].iloc[-1])
        except:
            pass
    return price_map


def get_latest_prices_parquet(intraday_parquet, tickers):
    """Fetch latest prices from parquet cache."""
    df = pd.read_parquet(intraday_parquet)
    price_map = {}
    for ticker in tickers:
        ticker_data = df[df["ticker"] == ticker]
        if not ticker_data.empty:
            price_map[ticker] = float(ticker_data["close"].iloc[-1])
    return price_map


def reconcile(state_dir, price_source="yfinance", intraday_parquet=None, interval="1m", ts=None):
    """
    Update mark-to-market prices.
    
    Args:
        state_dir: state directory
        price_source: "yfinance" or "intraday_parquet"
        intraday_parquet: path to parquet if using cache
        interval: interval for yfinance
        ts: timestamp (default now)
    """
    
    state = load_state(state_dir)
    
    # Get open position tickers
    pos_file = Path(state_dir) / "positions.csv"
    if pos_file.exists():
        pos_df = pd.read_csv(pos_file)
        tickers = pos_df["ticker"].unique().tolist()
    else:
        print("[WARN] No open positions")
        return
    
    # Fetch prices
    if price_source == "yfinance":
        price_map = get_latest_prices_yfinance(tickers, interval)
    elif price_source == "intraday_parquet":
        if intraday_parquet is None:
            raise ValueError("--intraday required for parquet source")
        price_map = get_latest_prices_parquet(intraday_parquet, tickers)
    else:
        raise ValueError(f"Unknown price source: {price_source}")
    
    if not price_map:
        print("[WARN] No prices fetched")
        return
    
    # Mark to market
    if ts is None:
        ts = datetime.now().isoformat()
    
    mark_to_market(state_dir, price_map, ts)
    
    # Print update
    state = load_state(state_dir)
    print(f"[OK] Mark-to-market reconciliation complete at {ts}")
    print(f"  Equity: ${state.get('equity', 0):.2f}")
    print(f"  Cash: ${state.get('cash', 0):.2f}")
    if "unrealized_pnl" in state:
        print(f"  Unrealized P&L: ${state['unrealized_pnl']:.2f}")


def main():
    ap = argparse.ArgumentParser(description="Reconcile broker mark-to-market")
    ap.add_argument("--state-dir", required=True, help="State directory")
    ap.add_argument("--price-source", choices=["yfinance", "intraday_parquet"], default="yfinance")
    ap.add_argument("--intraday", help="Path to intraday parquet (for cache mode)")
    ap.add_argument("--interval", default="1m", help="yfinance interval")
    
    args = ap.parse_args()
    
    reconcile(args.state_dir, args.price_source, args.intraday, args.interval)


if __name__ == "__main__":
    main()
