#!/usr/bin/env python3
"""
Quick forecast generator for new 5-ticker universe
OLD: AMD, CVX, XOM, JNJ, WMT
NEW: AMD, CVX, XOM, NVDA, MSFT
"""

import pandas as pd
import numpy as np
from pathlib import Path

def generate_new_tickers_forecast(month_str, output_dir="data/daily_new"):
    """
    Generate a simple forecast using ONLY the new 5 tickers
    """
    
    new_tickers = ["AMD", "CVX", "XOM", "NVDA", "MSFT"]
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a dummy forecast (parquet format) with 5 tickers
    # This is a PLACEHOLDER that will work with the existing system
    
    # For now: create CSV-based forecast
    forecast_data = []
    
    for ticker in new_tickers:
        forecast_data.append({
            "ticker": ticker,
            "side": "BUY",
            "entry": 100.0,  # Dummy
            "tp_price": 102.0,  # 2% TP
            "sl_price": 98.8,  # 1.2% SL
            "exposure": 200.0,  # 1/5 of capital
            "qty": 2,
            "strength": 0.7,  # Medium strength
        })
    
    df = pd.DataFrame(forecast_data)
    
    # Save as CSV
    output_csv = output_dir / "signals_with_gates.csv"
    df.to_csv(output_csv, index=False)
    
    print(f"✅ Generated forecast for NEW 5-ticker universe")
    print(f"   Tickers: {', '.join(new_tickers)}")
    print(f"   Output: {output_csv}")
    print(f"\nUsage:")
    print(f"  python paper/wf_paper_month.py \\")
    print(f"    --month {month_str} \\")
    print(f"    --forecast {output_csv} \\")
    print(f"    --intraday data/intraday_15m/{month_str}.parquet \\")
    print(f"    --execution-mode balanced \\")
    print(f"    --tp-pct 0.02 --sl-pct 0.012")
    
    return output_csv

if __name__ == "__main__":
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else "2025-12"
    generate_new_tickers_forecast(month)
