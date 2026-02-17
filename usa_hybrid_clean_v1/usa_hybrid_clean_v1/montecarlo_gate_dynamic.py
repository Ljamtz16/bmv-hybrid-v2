#!/usr/bin/env python3
"""
montecarlo_gate_dynamic.py
Ticker Gate DINÁMICO con recalculación semanal y rotación intra-mes.

Fase 2: En lugar de gate fijo mensual, recalcula MC cada semana
y permite rotación (drop bajo performers, add nuevos candidatos).

Usage:
    python montecarlo_gate_dynamic.py --month 2025-03 --rebalance-freq weekly --output-dir evidence/dynamic_gate_mar2025
"""

import argparse
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta
from montecarlo_gate import (
    load_intraday_data,
    run_monte_carlo_ticker,
    compute_score,
    TICKERS_UNIVERSE
)

def get_rebalance_dates(month_str, freq='weekly'):
    """
    Get rebalance dates for a month.
    
    Args:
        month_str: YYYY-MM
        freq: 'weekly' or 'biweekly'
    
    Returns:
        list of datetime.date for rebalance (Mondays or first trading day of week)
    """
    year, month = map(int, month_str.split('-'))
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(days=1)
    
    dates = []
    current = start
    
    # Find first Monday of month
    while current.weekday() != 0:  # 0=Monday
        current += timedelta(days=1)
        if current > end:
            break
    
    if freq == 'weekly':
        interval = 7
    elif freq == 'biweekly':
        interval = 14
    else:
        interval = 7
    
    while current <= end:
        dates.append(current.date())
        current += timedelta(days=interval)
    
    return dates


def run_dynamic_gate(
    intraday_df,
    month_str,
    rebalance_dates,
    lookback_days=20,
    mc_paths=300,
    top_k=4,
    max_rotation_per_rebalance=2,
    output_dir="evidence/dynamic_gate",
    seed=42
):
    """
    Run dynamic ticker gate with weekly rebalancing.
    
    Args:
        intraday_df: intraday OHLCV data
        month_str: YYYY-MM
        rebalance_dates: list of dates to recalculate gate
        lookback_days: MC window
        mc_paths: Monte Carlo paths
        top_k: number of tickers to select
        max_rotation_per_rebalance: max tickers to swap per rebalance
        output_dir: evidence directory
        seed: random seed
    
    Returns:
        dict with rebalance history and final portfolio
    """
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    rebalance_history = []
    current_portfolio = None
    
    for rebalance_idx, rebalance_date in enumerate(rebalance_dates):
        rebalance_str = rebalance_date.strftime("%Y-%m-%d")
        print(f"\n[REBALANCE {rebalance_idx + 1}/{len(rebalance_dates)}] Date: {rebalance_str}")
        print("=" * 80)
        
        # Calculate MC as of this rebalance date (using prior lookback_days)
        asof_date = (rebalance_date - timedelta(days=1)).strftime("%Y-%m-%d")
        
        print(f"Running Monte Carlo (asof={asof_date}, window={lookback_days}d, paths={mc_paths})...")
        
        # Run MC for all tickers
        results = []
        for ticker in TICKERS_UNIVERSE:
            try:
                metrics = run_monte_carlo_ticker(
                    intraday_df, ticker, asof_date, lookback_days, mc_paths,
                    tp_pct=0.016, sl_pct=0.01, max_hold_days=2,
                    block_size=4, seed=seed
                )
                if metrics:
                    score = compute_score(metrics)
                    results.append({
                        'ticker': ticker,
                        'score': score,
                        'metrics': metrics
                    })
            except Exception as e:
                print(f"  [WARN] {ticker} failed: {e}")
                continue
        
        # Sort by score (higher is better, less negative)
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Add rank
        for rank, r in enumerate(results, 1):
            r['rank'] = rank
        
        # Select top-K
        new_candidates = [r['ticker'] for r in results[:top_k]]
        
        if current_portfolio is None:
            # First rebalance: just select top-K
            current_portfolio = new_candidates
            rotation = {'added': new_candidates, 'dropped': [], 'kept': []}
            print(f"  Initial portfolio: {current_portfolio}")
        else:
            # Rotation logic: keep best performers, rotate out worst
            kept = [t for t in current_portfolio if t in new_candidates[:top_k + max_rotation_per_rebalance]]
            dropped = [t for t in current_portfolio if t not in kept]
            
            # Add new tickers to fill gaps (respect max_rotation)
            slots_available = min(top_k - len(kept), max_rotation_per_rebalance)
            added = []
            for candidate in new_candidates:
                if candidate not in kept and len(added) < slots_available:
                    added.append(candidate)
            
            current_portfolio = kept + added
            rotation = {'added': added, 'dropped': dropped, 'kept': kept}
            
            print(f"  Kept:    {kept}")
            print(f"  Dropped: {dropped}")
            print(f"  Added:   {added}")
            print(f"  → New portfolio: {current_portfolio}")
        
        # Save rebalance snapshot
        rebalance_record = {
            'rebalance_date': rebalance_str,
            'rebalance_idx': rebalance_idx + 1,
            'asof_date': asof_date,
            'portfolio': current_portfolio,
            'rotation': rotation,
            'top_10_ranking': [
                {
                    'rank': r['rank'],
                    'ticker': r['ticker'],
                    'score': float(r['score']),
                    'metrics': {k: float(v) if isinstance(v, (np.floating, float)) else v 
                                for k, v in r['metrics'].items()}
                }
                for r in results[:10]
            ]
        }
        
        rebalance_history.append(rebalance_record)
        
        # Save snapshot to file
        snapshot_file = output_path / f"rebalance_{rebalance_idx + 1}_{rebalance_date.strftime('%Y%m%d')}.json"
        with open(snapshot_file, 'w') as f:
            json.dump(rebalance_record, f, indent=2)
        print(f"  Saved: {snapshot_file}")
    
    # Final summary
    final_output = {
        'month': month_str,
        'config': {
            'lookback_days': lookback_days,
            'mc_paths': mc_paths,
            'top_k': top_k,
            'max_rotation_per_rebalance': max_rotation_per_rebalance,
            'rebalance_freq': 'weekly',
            'seed': seed
        },
        'rebalance_dates': [d.strftime("%Y-%m-%d") for d in rebalance_dates],
        'rebalance_history': rebalance_history,
        'final_portfolio': current_portfolio,
        'generated_at': datetime.now().isoformat()
    }
    
    output_file = output_path / "dynamic_gate.json"
    with open(output_file, 'w') as f:
        json.dump(final_output, f, indent=2)
    
    print(f"\n[OK] Dynamic gate saved: {output_file}")
    print(f"Final portfolio: {current_portfolio}")
    
    return final_output


def main():
    ap = argparse.ArgumentParser(description="Dynamic Monte Carlo Ticker Gate with Weekly Rebalancing")
    ap.add_argument("--month", required=True, help="Month (YYYY-MM)")
    ap.add_argument("--intraday", default="C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet", help="Intraday data")
    ap.add_argument("--rebalance-freq", choices=['weekly', 'biweekly'], default='weekly', help="Rebalance frequency")
    ap.add_argument("--lookback-days", type=int, default=20, help="MC lookback window")
    ap.add_argument("--mc-paths", type=int, default=300, help="Monte Carlo paths")
    ap.add_argument("--top-k", type=int, default=4, help="Number of tickers to select")
    ap.add_argument("--max-rotation", type=int, default=2, help="Max tickers to rotate per rebalance")
    ap.add_argument("--output-dir", default="evidence/dynamic_gate", help="Output directory")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    
    args = ap.parse_args()
    
    print("[Dynamic Ticker Gate - Intra-Month Rebalancing]")
    print(f"Month: {args.month} | Freq: {args.rebalance_freq} | Top-K: {args.top_k}")
    
    # Load data
    print(f"\nLoading intraday data: {args.intraday}")
    intraday_df = load_intraday_data(args.intraday)
    print(f"  {len(intraday_df)} rows loaded")
    
    # Get rebalance dates
    rebalance_dates = get_rebalance_dates(args.month, args.rebalance_freq)
    print(f"\nRebalance schedule ({len(rebalance_dates)} dates):")
    for i, d in enumerate(rebalance_dates, 1):
        print(f"  {i}. {d.strftime('%Y-%m-%d (%A)')}")
    
    # Run dynamic gate
    result = run_dynamic_gate(
        intraday_df,
        args.month,
        rebalance_dates,
        lookback_days=args.lookback_days,
        mc_paths=args.mc_paths,
        top_k=args.top_k,
        max_rotation_per_rebalance=args.max_rotation,
        output_dir=args.output_dir,
        seed=args.seed
    )
    
    print("\n" + "="*80)
    print("SUMMARY: Portfolio Evolution")
    print("="*80)
    for record in result['rebalance_history']:
        rot = record['rotation']
        print(f"\n{record['rebalance_date']} (Rebalance #{record['rebalance_idx']}):")
        print(f"  Portfolio: {record['portfolio']}")
        if rot['added']:
            print(f"  + Added: {rot['added']}")
        if rot['dropped']:
            print(f"  - Dropped: {rot['dropped']}")


if __name__ == "__main__":
    main()
