#!/usr/bin/env python3
"""
run_intraday_sim_2022_2025.py
Execute intraday paper trading simulation for full date range (2022-2025).
Runs wf_paper_month.py for each month, then consolidates all_trades.csv
"""

import argparse
import subprocess
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta


def get_months_in_range(start_date_str, end_date_str):
    """Generate list of months in YYYY-MM format between start_date and end_date."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return months


def run_wf_paper_month(month, **kwargs):
    """Execute wf_paper_month.py for a single month."""
    cmd = ["python", "paper/wf_paper_month.py", "--month", month]
    
    # Map kwargs to CLI args
    arg_mapping = {
        "capital": "--capital",
        "exposure_cap": "--exposure-cap",
        "max_open": "--max-open",
        "execution_mode": "--execution-mode",
        "max_hold_days": "--max-hold-days",
        "intraday": "--intraday",
        "evidence_dir": "--evidence-dir",
        "state_dir": "--state-dir",
        "forecast": "--forecast",
        "prices": "--prices",
        "tickers_file": "--tickers-file",
        "tickers": "--tickers",
        "tp_pct": "--tp-pct",
        "sl_pct": "--sl-pct",
        "commission": "--commission",
        "slippage_pct": "--slippage-pct",
    }
    
    for key, flag in arg_mapping.items():
        if key in kwargs and kwargs[key] is not None:
            cmd.append(flag)
            cmd.append(str(kwargs[key]))
    
    print(f"\n[RUN] {month}")
    print(f"  Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, cwd=".", capture_output=False)
    return result.returncode == 0


def consolidate_trades(evidence_dir, output_dir):
    """Consolidate all_trades.csv from monthly subdirectories."""
    evidence_path = Path(evidence_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    all_trades = []
    
    # Find all monthly subdirectories
    month_dirs = sorted([d for d in evidence_path.iterdir() if d.is_dir() and len(d.name) == 7])
    
    print(f"\n[CONSOLIDATE] Found {len(month_dirs)} month directories")
    
    for month_dir in month_dirs:
        trades_file = month_dir / "all_trades.csv"
        if trades_file.exists():
            df = pd.read_csv(trades_file)
            all_trades.append(df)
            print(f"  {month_dir.name}: {len(df)} trades")
        else:
            print(f"  {month_dir.name}: no all_trades.csv found")
    
    if all_trades:
        consolidated = pd.concat(all_trades, ignore_index=True)
        output_file = output_path / "all_trades.csv"
        consolidated.to_csv(output_file, index=False)
        print(f"\n[OK] Consolidated {len(consolidated)} trades → {output_file}")
        return consolidated
    else:
        print("\n[WARN] No trades found to consolidate")
        return None


def generate_summary(trades_df, output_dir):
    """Generate summary statistics from consolidated trades."""
    if trades_df is None or trades_df.empty:
        print("[WARN] Empty trades dataframe, skipping summary")
        return
    
    output_path = Path(output_dir)
    
    # Resolve PnL column
    pnl_col = "pnl"
    if pnl_col not in trades_df.columns:
        # Try alternative names
        for alt in ["pnl_pct", "profit", "return"]:
            if alt in trades_df.columns:
                pnl_col = alt
                break
    
    # Calculate metrics
    n_trades = len(trades_df)
    total_pnl = trades_df[pnl_col].sum()
    win_count = (trades_df[pnl_col] > 0).sum()
    loss_count = (trades_df[pnl_col] < 0).sum()
    win_rate = (win_count / n_trades * 100) if n_trades > 0 else 0
    
    gross_profit = trades_df[trades_df[pnl_col] > 0][pnl_col].sum()
    gross_loss = abs(trades_df[trades_df[pnl_col] < 0][pnl_col].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    
    summary = {
        "total_trades": n_trades,
        "total_pnl": float(total_pnl),
        "win_count": int(win_count),
        "loss_count": int(loss_count),
        "win_rate_pct": float(win_rate),
        "gross_profit": float(gross_profit),
        "gross_loss": float(gross_loss),
        "profit_factor": float(profit_factor) if profit_factor != float('inf') else None,
    }
    
    summary_file = output_path / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n[SUMMARY]")
    print(f"  Total trades: {n_trades}")
    print(f"  Total P&L: ${total_pnl:.2f}")
    print(f"  Win rate: {win_rate:.1f}% ({win_count}W / {loss_count}L)")
    print(f"  Profit factor: {profit_factor:.2f}x" if profit_factor != float('inf') else "  Profit factor: inf")
    print(f"  Summary → {summary_file}")


def main():
    ap = argparse.ArgumentParser(description="Run intraday paper trading for 2022-2025")
    ap.add_argument("--start-date", default="2022-01-01", help="Start date (YYYY-MM-DD)")
    ap.add_argument("--end-date", default="2025-12-31", help="End date (YYYY-MM-DD)")
    ap.add_argument("--capital", type=float, default=600, help="Initial capital")
    ap.add_argument("--exposure-cap", type=float, default=None, help="Exposure cap (default: capital)")
    ap.add_argument("--max-open", type=int, default=15, help="Max concurrent open positions")
    ap.add_argument("--execution-mode", choices=["intraday", "fast", "balanced", "conservative"], default="balanced")
    ap.add_argument("--max-hold-days", type=int, default=3, help="Max holding period")
    ap.add_argument("--intraday", required=True, help="Path to intraday parquet cache")
    ap.add_argument("--evidence-dir", default="evidence/paper_2022_2025_intraday", help="Base evidence directory")
    ap.add_argument("--state-dir", default="paper_state", help="Paper broker state directory")
    ap.add_argument("--forecast", default="data/daily/signals_with_gates.parquet")
    ap.add_argument("--prices", default="data/daily/ohlcv_daily.parquet")
    ap.add_argument("--tickers", default=None, help="Comma-separated tickers (optional)")
    ap.add_argument("--tickers-file", default=None, help="Tickers file path (optional)")
    ap.add_argument("--tp-pct", type=float, required=True, help="Take profit % (e.g., 0.016 for 1.6%)")
    ap.add_argument("--sl-pct", type=float, required=True, help="Stop loss % (e.g., 0.01 for 1%)")
    ap.add_argument("--commission", type=float, default=0.0, help="Commission per trade")
    ap.add_argument("--slippage-pct", type=float, default=0.0, help="Slippage fraction")
    ap.add_argument("--skip-consolidate", action="store_true", help="Skip consolidation step")
    
    args = ap.parse_args()
    
    # Set exposure cap default
    if args.exposure_cap is None:
        args.exposure_cap = args.capital
    
    # Get month list
    months = get_months_in_range(args.start_date, args.end_date)
    print(f"\n[PLAN] Running {len(months)} months from {args.start_date} to {args.end_date}")
    print(f"  Parameters:")
    print(f"    Capital: ${args.capital:.0f}")
    print(f"    Exposure cap: ${args.exposure_cap:.0f}")
    print(f"    TP: {args.tp_pct*100:.1f}% | SL: {args.sl_pct*100:.1f}%")
    print(f"    Mode: {args.execution_mode}")
    print(f"  Output: {args.evidence_dir}")
    
    # Run monthly sims
    failed_months = []
    for month in months:
        kwargs = {
            "capital": args.capital,
            "exposure_cap": args.exposure_cap,
            "max_open": args.max_open,
            "execution_mode": args.execution_mode,
            "max_hold_days": args.max_hold_days,
            "intraday": args.intraday,
            "evidence_dir": args.evidence_dir,
            "state_dir": args.state_dir,
            "forecast": args.forecast,
            "prices": args.prices,
            "tickers": args.tickers,
            "tickers_file": args.tickers_file,
            "tp_pct": args.tp_pct,
            "sl_pct": args.sl_pct,
            "commission": args.commission,
            "slippage_pct": args.slippage_pct,
        }
        
        if not run_wf_paper_month(month, **kwargs):
            failed_months.append(month)
            print(f"  [FAIL] {month}")
    
    print(f"\n[STATUS] {len(months) - len(failed_months)}/{len(months)} months successful")
    if failed_months:
        print(f"  Failed: {', '.join(failed_months)}")
    
    # Consolidate
    if not args.skip_consolidate:
        trades_df = consolidate_trades(args.evidence_dir, args.evidence_dir)
        generate_summary(trades_df, args.evidence_dir)
    
    print("\n[DONE]")


if __name__ == "__main__":
    main()
