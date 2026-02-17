#!/usr/bin/env python3
"""
Merge old 5 tickers + new 2 tickers for comparative analysis
OLD: AMD, CVX, XOM, JNJ, WMT (existing 2025-12.parquet)
NEW: NVDA, MSFT (just downloaded 2025-12_NEW.parquet)

Create MERGED dataset with both universes for comparison
"""

import pandas as pd
from pathlib import Path

print("=" * 90)
print("PREPARING MERGED DATASET: OLD (5) + NEW (2) TICKERS")
print("=" * 90)

# Load both datasets
old_path = Path("data/intraday_15m/2025-12.parquet")
new_path = Path("data/intraday_15m/2025-12_NEW.parquet")

if not old_path.exists():
    print(f"❌ {old_path} not found")
    exit(1)

if not new_path.exists():
    print(f"❌ {new_path} not found")
    exit(1)

print(f"\n✅ Loading old data: {old_path}")
df_old = pd.read_parquet(old_path)
print(f"   Shape: {df_old.shape}")

print(f"\n✅ Loading new data: {new_path}")
df_new = pd.read_parquet(new_path)
print(f"   Shape: {df_new.shape}")

# Merge into combined dataset
print(f"\n✅ Merging datasets...")
df_merged = pd.concat([df_old, df_new], ignore_index=True)
print(f"   Combined shape: {df_merged.shape}")

# Get unique tickers
tickers_old = df_old[df_old.columns[df_old.columns.get_level_values(1) != ''][0].iloc[0] if isinstance(df_old.columns, pd.MultiIndex) else df_old.columns].unique() if isinstance(df_old.columns, pd.MultiIndex) else df_old.get('ticker', []).unique() if 'ticker' in df_old.columns else []

print(f"\n📊 DATASET COMPOSITION:")
print(f"   OLD data tickers: {df_old.shape}")
print(f"   NEW data tickers (NVDA, MSFT): {df_new.shape}")
print(f"   TOTAL: {df_merged.shape}")

# Save merged
merged_path = Path("data/intraday_15m/2025-12_MERGED.parquet")
df_merged.to_parquet(merged_path)
print(f"\n✅ Saved merged data to: {merged_path}")

print(f"\n" + "=" * 90)
print(f"NEXT STEP: Run walk-forward with merged dataset")
print(f"=" * 90)
print(f"\nCommand:")
print(f"  python paper/wf_paper_month.py \\")
print(f"    --month \"2025-12\" \\")
print(f"    --execution-mode balanced \\")
print(f"    --max-hold-days 2 \\")
print(f"    --tp-pct 0.02 \\")
print(f"    --sl-pct 0.012 \\")
print(f"    --intraday {merged_path}")
print(f"\nThis will simulate trades using ALL 7 tickers (AMD, CVX, XOM, JNJ, WMT, NVDA, MSFT)")
print(f"Then filter results to compare:")
print(f"  - OLD universe (5): AMD, CVX, XOM, JNJ, WMT = $38.09")
print(f"  - NEW universe (5): AMD, CVX, XOM, NVDA, MSFT = ?")
print(f"=" * 90)
