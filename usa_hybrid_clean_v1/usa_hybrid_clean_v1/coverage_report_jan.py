#!/usr/bin/env python3
"""
Compute 15m RTH coverage per ticker for January 2026 intraday cache.
Assumes RTH 9:30-16:00 NY -> 6.5h -> 26 candles per day.
"""
import pandas as pd
from pathlib import Path

intraday_path = Path('data/intraday_15m/2026-01_COMBINED_LONG.parquet')
df = pd.read_parquet(intraday_path)

# Normalize datetime to NY; yfinance is UTC, RTH window: 14:30-21:00 UTC
# We'll count candles with minute in {30, 45, 0, 15} within the RTH hours

df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
df['date'] = df['datetime'].dt.date

# Expected per trading day
expected_per_day = 26

summary = []
for t in sorted(df['ticker'].unique()):
    sub = df[df['ticker'] == t]
    days = sorted(sub['date'].unique())
    present = 0
    for d in days:
        present += len(sub[sub['date'] == d])
    expected = len(days) * expected_per_day
    coverage = present / expected if expected > 0 else 0
    summary.append({
        'ticker': t,
        'days': len(days),
        'present_candles': present,
        'expected_candles': expected,
        'coverage_ratio': coverage,
    })

out = pd.DataFrame(summary)
print(out.to_string(index=False))
