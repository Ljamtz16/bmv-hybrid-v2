#!/usr/bin/env python3
"""
Merge the old 5-ticker cache with the new NVDA/MSFT cache into a clean long-format
parquet compatible with intraday_simulator.
"""

import ast
import pandas as pd
from pathlib import Path


def to_long(df: pd.DataFrame) -> pd.DataFrame:
    """Convert wide (multi-index or stringified tuples) to long OHLCV format."""
    # Already long
    if set(["datetime", "ticker", "open", "high", "low", "close", "volume"]).issubset(df.columns):
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        return df[["datetime", "ticker", "open", "high", "low", "close", "volume"]]

    cols = df.columns
    # Parse stringified tuple columns if needed
    if isinstance(cols[0], str) and cols[0].startswith("('"):
        cols = [ast.literal_eval(c) if isinstance(c, str) and c.startswith("('") else c for c in cols]
        df = df.copy()
        df.columns = cols
    elif isinstance(cols[0], tuple):
        df = df.copy()
    else:
        raise ValueError("Unrecognized column format for wide intraday data")

    cols = df.columns
    # Identify datetime column
    dt_candidates = [c for c in cols if (isinstance(c, tuple) and c[0] == "datetime") or c == "datetime"]
    if not dt_candidates:
        raise ValueError("No datetime column found")
    dt_col = dt_candidates[0]

    # Identify tickers from OHLCV tuples
    tickers = set()
    for col in cols:
        if isinstance(col, tuple) and len(col) == 2 and col[0] in ["open", "high", "low", "close", "volume"]:
            tickers.add(col[1])

    records = []
    for ticker in tickers:
        temp = pd.DataFrame({"datetime": df[dt_col], "ticker": ticker})
        for field in ["open", "high", "low", "close", "volume"]:
            col_name = (field, ticker)
            if col_name in df.columns:
                temp[field] = df[col_name]
        # Drop rows with no OHLC data
        temp = temp.dropna(subset=["open", "high", "low", "close"], how="all")
        records.append(temp)

    out = pd.concat(records, ignore_index=True)
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True)
    return out[["datetime", "ticker", "open", "high", "low", "close", "volume"]]


def main():
    print("=" * 90)
    print("CLEAN MERGE TO LONG FORMAT")
    print("=" * 90)

    old_path = Path("data/intraday_15m/2025-12.parquet")
    new_path = Path("data/intraday_15m/2025-12_NEW.parquet")

    print(f"\n[1] Loading {old_path}...")
    df_old = pd.read_parquet(old_path)
    print(f"    Rows: {len(df_old)}, Cols: {len(df_old.columns)}")

    print(f"\n[2] Loading {new_path}...")
    df_new = pd.read_parquet(new_path)
    print(f"    Rows: {len(df_new)}, Cols: {len(df_new.columns)}")

    print("\n[3] Converting to long format...")
    df_old_long = to_long(df_old)
    df_new_long = to_long(df_new)
    print(f"    OLD long: {df_old_long.shape}, tickers={sorted(df_old_long['ticker'].unique())}")
    print(f"    NEW long: {df_new_long.shape}, tickers={sorted(df_new_long['ticker'].unique())}")

    print("\n[4] Concatenating...")
    df_merged = pd.concat([df_old_long, df_new_long], ignore_index=True)
    df_merged = df_merged.sort_values(["datetime", "ticker"]).reset_index(drop=True)
    print(f"    Merged: {df_merged.shape}")

    out_path = Path("data/intraday_15m/2025-12_COMBINED_LONG.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_merged.to_parquet(out_path)
    print(f"\n✅ Saved to: {out_path}")

    print("\n" + "=" * 90)
    print("Run walk-forward with this file:")
    print("python paper/wf_paper_month.py --month '2025-12' --execution-mode balanced --max-hold-days 2 --tp-pct 0.02 --sl-pct 0.012 --intraday data/intraday_15m/2025-12_COMBINED_LONG.parquet")
    print("=" * 90)


if __name__ == "__main__":
    main()
