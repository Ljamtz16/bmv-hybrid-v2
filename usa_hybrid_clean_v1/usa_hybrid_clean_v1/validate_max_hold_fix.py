#!/usr/bin/env python3
"""
Validate max_hold_days fix: ensure TIMEOUT respects trading sessions, not calendar days.

Check:
1. max_hold_days=2 → trades close at EOD of Day 1 (not 48h calendar)
2. No TIMEOUT extends beyond (entry_date + max_hold_days - 1) trading days
3. Weekends/holidays don't inflate hold time
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

def validate_hold_window(trades_df, max_hold_days=2):
    """
    Validate that TIMEOUT trades respect max_hold_days trading sessions.
    
    Returns: dict with validation results
    """
    issues = []
    
    if trades_df.empty:
        return {"valid": True, "issues": [], "summary": "No trades to validate"}
    
    # Convert to datetime
    trades_df = trades_df.copy()
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
    trades_df["entry_date"] = trades_df["entry_time"].dt.date
    trades_df["exit_date"] = trades_df["exit_time"].dt.date
    
    # Filter TIMEOUT trades
    timeouts = trades_df[trades_df["outcome"] == "TIMEOUT"].copy()
    
    if timeouts.empty:
        return {"valid": True, "issues": [], "summary": f"No TIMEOUT trades (all hit TP/SL)"}
    
    # Get unique trading dates from all trades
    all_dates = set()
    all_dates.update(trades_df["entry_date"].unique())
    all_dates.update(trades_df["exit_date"].unique())
    unique_trade_dates = sorted(all_dates)
    
    print(f"[VALIDATE] {len(timeouts)} TIMEOUT trades to check")
    print(f"[VALIDATE] Trading dates in dataset: {unique_trade_dates[:3]} ... {unique_trade_dates[-3:]}")
    
    for idx, row in timeouts.iterrows():
        ticker = row["ticker"]
        entry_date = row["entry_date"]
        exit_date = row["exit_date"]
        entry_time = row["entry_time"]
        exit_time = row["exit_time"]
        
        # Find entry_date position in unique_trade_dates
        if entry_date not in unique_trade_dates:
            issues.append(f"{ticker} entry_date {entry_date} not in trading dates")
            continue
        
        entry_idx = unique_trade_dates.index(entry_date)
        expected_timeout_idx = entry_idx + (max_hold_days - 1)
        
        if expected_timeout_idx >= len(unique_trade_dates):
            # Not enough data → should have been flagged as NO_DATA_TIMEOUT
            if row["outcome"] == "TIMEOUT":
                issues.append(f"{ticker} TIMEOUT beyond data window (entry {entry_date}, expected {max_hold_days-1} days forward)")
            continue
        
        expected_timeout_date = unique_trade_dates[expected_timeout_idx]
        
        # Validate exit_date matches expected
        if exit_date != expected_timeout_date:
            # Allow exit on or before expected (if TP/SL hit earlier, but outcome should not be TIMEOUT)
            if exit_date > expected_timeout_date:
                issues.append(
                    f"{ticker}: TIMEOUT exit {exit_date} AFTER expected {expected_timeout_date} "
                    f"(entry {entry_date}, max_hold={max_hold_days})"
                )
        
        # Check hold time in calendar days (should not exceed max_hold_days + weekends)
        calendar_days = (exit_date - entry_date).days
        trading_days_held = unique_trade_dates.index(exit_date) - entry_idx
        
        if trading_days_held > (max_hold_days - 1):
            issues.append(
                f"{ticker}: held {trading_days_held} trading days (expected max {max_hold_days-1}), "
                f"entry={entry_date}, exit={exit_date}"
            )
    
    # Summary stats - fix timedelta handling
    timeouts_copy = timeouts.copy()
    timeouts_copy["calendar_days"] = timeouts_copy.apply(
        lambda row: (row["exit_date"] - row["entry_date"]).days,
        axis=1
    )
    
    summary = {
        "total_timeouts": len(timeouts),
        "calendar_days_mean": timeouts_copy["calendar_days"].mean(),
        "calendar_days_max": timeouts_copy["calendar_days"].max(),
        "issues_count": len(issues),
    }
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "summary": summary,
    }


def main():
    print("=" * 80)
    print("VALIDATING max_hold_days FIX")
    print("=" * 80)
    
    # Test on December 2025 A/B results (FIXED version)
    evidence_dir = Path("evidence/paper_dec_2025_FIXED_old")
    summary_file = evidence_dir / "all_trades.csv"
    
    if not summary_file.exists():
        print(f"[ERROR] Summary file not found: {summary_file}")
        print("[INFO] Run December A/B first to generate test data")
        return
    
    trades = pd.read_csv(summary_file)
    print(f"\n[INFO] Loaded {len(trades)} trades from {summary_file}")
    print(f"[INFO] Outcomes: {trades['outcome'].value_counts().to_dict()}")
    
    # Validate with max_hold_days=2 (as used in wf_paper_month.py)
    result = validate_hold_window(trades, max_hold_days=2)
    
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    print(f"Valid: {result['valid']}")
    print(f"Summary: {result['summary']}")
    
    if result["issues"]:
        print(f"\n❌ ISSUES FOUND ({len(result['issues'])}):")
        for i, issue in enumerate(result["issues"][:10], 1):
            print(f"  {i}. {issue}")
        if len(result["issues"]) > 10:
            print(f"  ... and {len(result['issues']) - 10} more")
    else:
        print("\n✅ NO ISSUES: max_hold_days logic is correct")
    
    # Check a few specific examples
    print("\n" + "=" * 80)
    print("SAMPLE TIMEOUT TRADES")
    print("=" * 80)
    
    timeouts = trades[trades["outcome"] == "TIMEOUT"].copy()
    if not timeouts.empty:
        timeouts["entry_time"] = pd.to_datetime(timeouts["entry_time"])
        timeouts["exit_time"] = pd.to_datetime(timeouts["exit_time"])
        timeouts["calendar_days"] = (timeouts["exit_time"] - timeouts["entry_time"]).dt.days
        timeouts["hold_hours"] = timeouts["hold_hours"].round(1)
        
        sample = timeouts.head(10)[["ticker", "entry_time", "exit_time", "calendar_days", "hold_hours", "pnl"]]
        print(sample.to_string(index=False))
        
        print(f"\nCalendar days held (TIMEOUT trades):")
        print(f"  Mean: {timeouts['calendar_days'].mean():.1f}")
        print(f"  Median: {timeouts['calendar_days'].median():.1f}")
        print(f"  Max: {timeouts['calendar_days'].max()}")
        print(f"  Min: {timeouts['calendar_days'].min()}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
