#!/usr/bin/env python3
"""
Debug intraday simulator - check wide→long conversion and entry logic
"""

import pandas as pd
import sys
sys.path.insert(0, 'paper')
from intraday_simulator import _reshape_wide_to_long

# Load Dec 2025 data
print("=" * 80)
print("LOADING DATA")
print("=" * 80)
df_wide = pd.read_parquet('data/intraday_15m/2025-12.parquet')
print(f"\nWide format shape: {df_wide.shape}")
print(f"Wide format columns (first 10): {df_wide.columns[:10].tolist()}")
print(f"\nFirst row (wide):")
print(df_wide.iloc[0])

# Convert to long
print("\n" + "=" * 80)
print("CONVERTING TO LONG")
print("=" * 80)
df_long = _reshape_wide_to_long(df_wide)
print(f"\nLong format shape: {df_long.shape}")
print(f"Long format columns: {df_long.columns.tolist()}")
print(f"\nLong format head:")
print(df_long.head(20))

# Filter for XOM on 2025-12-01
print("\n" + "=" * 80)
print("XOM DATA FOR 2025-12-01")
print("=" * 80)
xom_dec1 = df_long[(df_long['ticker'] == 'XOM') & (df_long['datetime'] >= '2025-12-01') & (df_long['datetime'] < '2025-12-02')]
print(f"\nXOM 2025-12-01 shape: {xom_dec1.shape}")
print(f"\nXOM 2025-12-01 data:")
print(xom_dec1[['datetime', 'open', 'high', 'low', 'close']].to_string())

# Load trade plan for Dec 01
print("\n" + "=" * 80)
print("TRADE PLAN FOR 2025-12-01")
print("=" * 80)
trade_plan = pd.read_csv('evidence/paper_dec_2025_15m/2025-12-01/trade_plan.csv')
xom_plan = trade_plan[trade_plan['ticker'] == 'XOM']
print(f"\nXOM plan:")
print(xom_plan[['ticker', 'side', 'entry', 'tp_price', 'sl_price', 'date', 'qty']].to_string())

# Compare entry price vs actual open
if not xom_dec1.empty and not xom_plan.empty:
    plan_entry = float(xom_plan.iloc[0]['entry'])
    actual_open = float(xom_dec1.iloc[0]['open'])
    first_high = float(xom_dec1.iloc[0]['high'])
    first_low = float(xom_dec1.iloc[0]['low'])
    plan_sl = float(xom_plan.iloc[0]['sl_price'])
    plan_tp = float(xom_plan.iloc[0]['tp_price'])
    
    print("\n" + "=" * 80)
    print("ENTRY COMPARISON")
    print("=" * 80)
    print(f"Plan entry price (from asof_date): ${plan_entry:.2f}")
    print(f"Actual open (first vela):          ${actual_open:.2f}")
    print(f"First vela high:                   ${first_high:.2f}")
    print(f"First vela low:                    ${first_low:.2f}")
    print(f"Plan TP:                           ${plan_tp:.2f}")
    print(f"Plan SL:                           ${plan_sl:.2f}")
    
    print(f"\n❌ PROBLEM: Entry price is ${(plan_entry - actual_open):.2f} different from actual open!")
    print(f"   - Using plan_entry ({plan_entry}) vs actual market price ({actual_open})")
    print(f"   - This is because entry={plan_entry} comes from asof_date (NOV 28), not sim_date (DEC 01)")
    
    # Check if SL would hit in first candle using plan entry
    if first_low <= plan_sl:
        print(f"\n✅ SL HIT: Using entry={plan_entry}, first_low={first_low} <= sl={plan_sl}")
        print(f"   This is why ALL trades hit SL immediately!")
    
    # Check what should happen with actual open
    print(f"\n💡 WHAT SHOULD HAPPEN:")
    print(f"   - Entry at actual open: ${actual_open}")
    print(f"   - Recalculate TP/SL based on actual entry")
    print(f"   - Current TP distance: {((plan_tp - plan_entry) / plan_entry * 100):.2f}%")
    print(f"   - Current SL distance: {((plan_entry - plan_sl) / plan_entry * 100):.2f}%")
