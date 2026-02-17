#!/usr/bin/env python3
"""
paper/validate_setup.py
Pre-flight check for paper trading 15m operations.

Usage:
    python paper/validate_setup.py --check all
    python paper/validate_setup.py --check intraday
    python paper/validate_setup.py --check core-pipeline
    python paper/validate_setup.py --check broker
"""

import argparse
import pandas as pd
import json
from pathlib import Path
from datetime import datetime


def check_intraday_cache(cache_path, verbose=False):
    """Check intraday parquet cache."""
    print("[1] Checking Intraday Cache")
    
    cache_file = Path(cache_path)
    
    if not cache_file.exists():
        print(f"  ❌ Cache not found: {cache_path}")
        return False
    
    try:
        df = pd.read_parquet(cache_file)
        
        # Validate columns
        required_cols = ['datetime', 'ticker', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            print(f"  ❌ Missing columns: {missing}")
            return False
        
        # Validate data
        if len(df) == 0:
            print(f"  ❌ Cache is empty")
            return False
        
        if df['datetime'].isna().any():
            print(f"  ❌ NaN values in datetime")
            return False
        
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # Print summary
        print(f"  ✅ Cache valid")
        print(f"     Rows: {len(df):,}")
        print(f"     Tickers: {df['ticker'].nunique()} ({', '.join(df['ticker'].unique())})")
        print(f"     Date range: {df['datetime'].min()} to {df['datetime'].max()}")
        print(f"     Interval: Intraday (typically 15m)")
        
        return True
    except Exception as e:
        print(f"  ❌ Error loading cache: {e}")
        return False


def check_core_pipeline(signals_path, prices_path, verbose=False):
    """Check core pipeline data availability."""
    print("\n[2] Checking Core Pipeline")
    
    signals_file = Path(signals_path)
    prices_file = Path(prices_path)
    
    results = []
    
    # Check signals
    if not signals_file.exists():
        print(f"  ❌ Signals not found: {signals_path}")
        results.append(False)
    else:
        try:
            df = pd.read_parquet(signals_file)
            if len(df) == 0:
                print(f"  ❌ Signals is empty")
                results.append(False)
            else:
                latest_date = df['datetime'].max() if 'datetime' in df.columns else 'unknown'
                print(f"  ✅ Signals: {len(df):,} rows, latest {latest_date}")
                results.append(True)
        except Exception as e:
            print(f"  ❌ Error loading signals: {e}")
            results.append(False)
    
    # Check prices
    if not prices_file.exists():
        print(f"  ❌ Prices not found: {prices_path}")
        results.append(False)
    else:
        try:
            df = pd.read_parquet(prices_file)
            if len(df) == 0:
                print(f"  ❌ Prices is empty")
                results.append(False)
            else:
                latest_date = df['datetime'].max() if 'datetime' in df.columns else 'unknown'
                print(f"  ✅ Prices: {len(df):,} rows, latest {latest_date}")
                results.append(True)
        except Exception as e:
            print(f"  ❌ Error loading prices: {e}")
            results.append(False)
    
    return all(results)


def check_broker_state(state_dir, verbose=False):
    """Check paper broker state."""
    print("\n[3] Checking Broker State")
    
    state_dir = Path(state_dir)
    
    if not state_dir.exists():
        print(f"  ⚠️  State directory not found: {state_dir}")
        print(f"     (Create with: python paper/paper_broker.py init --cash 500 --state-dir {state_dir})")
        return False
    
    state_file = state_dir / "state.json"
    
    if not state_file.exists():
        print(f"  ❌ state.json not found in {state_dir}")
        return False
    
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        print(f"  ✅ Broker state loaded")
        print(f"     Cash: ${state.get('cash', 0):.2f}")
        print(f"     Positions: {len(state.get('positions', {}))}")
        print(f"     Timestamp: {state.get('timestamp', 'N/A')}")
        
        # Check audit logs exist
        required_files = ['orders.csv', 'fills.csv', 'positions.csv', 'pnl_ledger.csv']
        missing = [f for f in required_files if not (state_dir / f).exists()]
        
        if missing:
            print(f"  ⚠️  Missing audit files: {missing}")
            print(f"     (They will be created on first execution)")
        else:
            print(f"  ✅ All audit logs present")
        
        return True
    except Exception as e:
        print(f"  ❌ Error loading state.json: {e}")
        return False


def check_modules():
    """Check all paper trading modules are importable."""
    print("\n[4] Checking Python Modules")
    
    modules = [
        ('paper.intraday_data', 'Intraday data download'),
        ('paper.intraday_simulator', 'Intraday simulator'),
        ('paper.metrics', 'Metrics calculation'),
        ('paper.paper_broker', 'Paper broker'),
        ('paper.paper_executor', 'Paper executor'),
        ('paper.paper_reconciler', 'Paper reconciler'),
        ('paper.wf_paper_month', 'Walk-forward month'),
        ('paper.test_paper_integration', 'Integration tests'),
    ]
    
    results = []
    for module_name, description in modules:
        try:
            __import__(module_name)
            print(f"  ✅ {description}")
            results.append(True)
        except Exception as e:
            print(f"  ❌ {description}: {e}")
            results.append(False)
    
    return all(results)


def validate_trade_plan(trade_plan_csv, expected_asof_date=None):
    """Validate a generated trade_plan.csv."""
    print("\n[5] Validating Trade Plan")
    
    plan_file = Path(trade_plan_csv)
    
    if not plan_file.exists():
        print(f"  ❌ Trade plan not found: {trade_plan_csv}")
        return False
    
    try:
        df = pd.read_csv(plan_file)
        
        # Check required columns
        required = ['ticker', 'qty', 'entry_price']
        missing = [c for c in required if c not in df.columns]
        if missing:
            print(f"  ❌ Missing columns: {missing}")
            return False
        
        # Check asof_date if expected
        if expected_asof_date:
            unique_dates = df['asof_date'].unique() if 'asof_date' in df.columns else ['N/A']
            if unique_dates[0] != expected_asof_date:
                print(f"  ❌ asof_date mismatch: expected {expected_asof_date}, got {unique_dates[0]}")
                return False
        
        # Check exposure
        if 'exposure' in df.columns:
            total_exposure = df['exposure'].sum()
            cap = 500  # Hardcoded for validation
            if total_exposure > cap * 1.05:  # 5% tolerance
                print(f"  ⚠️  Exposure {total_exposure:.2f} exceeds cap {cap}")
        
        # Summary
        print(f"  ✅ Trade plan valid")
        print(f"     Trades: {len(df)}")
        print(f"     Tickers: {', '.join(df['ticker'].unique())}")
        print(f"     Total qty: {df['qty'].sum()}")
        if 'asof_date' in df.columns:
            print(f"     asof_date: {df['asof_date'].unique()[0]}")
        
        return True
    except Exception as e:
        print(f"  ❌ Error validating trade plan: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="Paper trading setup validation")
    ap.add_argument("--check", choices=['all', 'intraday', 'core-pipeline', 'broker', 'modules', 'trade-plan'], 
                    default='all', help="Which check to run")
    ap.add_argument("--intraday", default="data/intraday_15m/2025-09.parquet", help="Intraday cache path")
    ap.add_argument("--signals", default="data/daily/signals_with_gates.parquet", help="Signals path")
    ap.add_argument("--prices", default="data/daily/ohlcv_daily.parquet", help="Prices path")
    ap.add_argument("--state-dir", default="paper_state", help="Broker state directory")
    ap.add_argument("--trade-plan", help="Trade plan CSV to validate (optional)")
    ap.add_argument("--expected-asof-date", help="Expected asof_date for trade plan (YYYY-MM-DD)")
    ap.add_argument("--verbose", action="store_true")
    
    args = ap.parse_args()
    
    print("=" * 60)
    print("PAPER TRADING SETUP VALIDATION")
    print("=" * 60)
    
    results = {}
    
    if args.check in ['all', 'intraday']:
        results['intraday'] = check_intraday_cache(args.intraday, args.verbose)
    
    if args.check in ['all', 'core-pipeline']:
        results['core'] = check_core_pipeline(args.signals, args.prices, args.verbose)
    
    if args.check in ['all', 'broker']:
        results['broker'] = check_broker_state(args.state_dir, args.verbose)
    
    if args.check in ['all', 'modules']:
        results['modules'] = check_modules()
    
    if args.check == 'trade-plan' and args.trade_plan:
        results['trade-plan'] = validate_trade_plan(args.trade_plan, args.expected_asof_date)
    
    # Summary
    print("\n" + "=" * 60)
    if all(results.values()):
        print("✅ ALL CHECKS PASSED - Ready for operations!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"❌ CHECKS FAILED: {', '.join(failed)}")
        print("   Fix issues above and try again")
    print("=" * 60)
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    exit(main())
