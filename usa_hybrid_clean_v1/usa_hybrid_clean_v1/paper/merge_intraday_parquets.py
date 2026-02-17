#!/usr/bin/env python3
"""
paper/merge_intraday_parquets.py
Merge multiple weekly intraday parquets into a single monthly file.

Usage:
    python paper/merge_intraday_parquets.py --input-pattern "data/intraday_15m/2025-09_w*.parquet" --out "data/intraday_15m/2025-09.parquet"
"""

import argparse
import pandas as pd
import glob
from pathlib import Path


def merge_parquets(input_pattern, output_file, verbose=False):
    """
    Merge parquets matching pattern into single file.
    
    Args:
        input_pattern: glob pattern (e.g., "data/intraday_15m/2025-09_w*.parquet")
        output_file: output path
        verbose: print details
    
    Returns:
        count of files merged, total rows
    """
    
    # Find all matching files
    files = sorted(glob.glob(input_pattern))
    
    if not files:
        print(f"[ERROR] No files matching pattern: {input_pattern}")
        return 0, 0
    
    if verbose:
        print(f"[INFO] Found {len(files)} files:")
        for f in files:
            print(f"  {f}")
    
    # Load and concatenate
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
            if verbose:
                print(f"  {f}: {len(df)} rows")
        except Exception as e:
            print(f"[WARN] Failed to load {f}: {e}")
            continue
    
    if not dfs:
        print("[ERROR] No files loaded successfully")
        return 0, 0
    
    # Merge
    merged = pd.concat(dfs, ignore_index=True)
    
    # Ensure datetime column
    if 'datetime' in merged.columns:
        merged['datetime'] = pd.to_datetime(merged['datetime'])
        merged = merged.sort_values('datetime').reset_index(drop=True)
    
    # Save
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(output_path, index=False)
    
    if verbose:
        print(f"\n[OK] Merged into: {output_path}")
        print(f"  Total rows: {len(merged)}")
        print(f"  Date range: {merged['datetime'].min()} to {merged['datetime'].max()}" if 'datetime' in merged.columns else "")
        print(f"  Tickers: {merged['ticker'].nunique() if 'ticker' in merged.columns else 'N/A'}")
    
    return len(files), len(merged)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Merge intraday parquet files")
    ap.add_argument("--input-pattern", required=True, help="Glob pattern (e.g., 'data/intraday_15m/2025-09_w*.parquet')")
    ap.add_argument("--out", required=True, help="Output parquet file")
    ap.add_argument("--verbose", action="store_true")
    
    args = ap.parse_args()
    
    files_merged, total_rows = merge_parquets(args.input_pattern, args.out, verbose=args.verbose)
    
    if files_merged == 0:
        exit(1)
    
    print(f"\n✅ Merged {files_merged} files into {total_rows} rows")
