#!/usr/bin/env python3
"""
paper/wf_paper_month.py
Walk-forward paper simulation for a full month, day by day.
"""

import argparse
import pandas as pd
import subprocess
import json
from pathlib import Path
from datetime import datetime, timedelta
from intraday_simulator import simulate_trades
from metrics import summary_stats, equity_curve


def get_weekday_range(month_str):
    """Get list of weekdays in a month (YYYY-MM)."""
    year, month = map(int, month_str.split("-"))
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(days=1)
    
    weekdays = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            weekdays.append(current)
        current += timedelta(days=1)
    
    return weekdays


def get_asof_date(trade_date):
    """Get T-1 US business day for a given trade_date (skip weekends, no holidays)."""
    asof = trade_date - timedelta(days=1)
    # Skip weekends (5=Sat, 6=Sun)
    while asof.weekday() >= 5:
        asof -= timedelta(days=1)
    return asof.strftime("%Y-%m-%d")


def parse_ticker_list(raw_list):
    tokens = [] if raw_list is None else raw_list.replace("\n", ",").split(",")
    cleaned = []
    seen = set()
    for t in tokens:
        tkr = t.strip().upper()
        if not tkr or tkr in seen:
            continue
        cleaned.append(tkr)
        seen.add(tkr)
    return cleaned


def load_tickers_from_file(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tickers file not found: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            if "selected_tickers" in data and isinstance(data["selected_tickers"], list):
                return parse_ticker_list(",".join(map(str, data["selected_tickers"])))
            if "tickers" in data and isinstance(data["tickers"], list):
                return parse_ticker_list(",".join(map(str, data["tickers"])))
        if isinstance(data, list):
            return parse_ticker_list(",".join(map(str, data)))
        raise ValueError(f"Unsupported JSON structure for tickers in {path}")

    # Fallback: text/CSV with comma or newline separation
    text = path.read_text()
    tokens = text.replace("\n", ",").split(",")
    return parse_ticker_list(",".join(tokens))


def filter_forecast_universe(forecast_path, tickers, output_path):
    suffix = Path(forecast_path).suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(forecast_path)
    elif suffix == ".csv":
        df = pd.read_csv(forecast_path)
    else:
        raise ValueError(f"Unsupported forecast format: {suffix}")

    if "ticker" not in df.columns:
        raise ValueError("Forecast missing 'ticker' column; cannot filter universe")

    df_filtered = df[df["ticker"].isin(tickers)].copy()
    if df_filtered.empty:
        raise ValueError("Filtered forecast is empty after applying ticker universe")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".parquet":
        df_filtered.to_parquet(output_path, index=False)
    else:
        df_filtered.to_csv(output_path, index=False)

    print(f"[INFO] Forecast filtered to {len(df_filtered)} rows and {len(tickers)} tickers -> {output_path}")
    return output_path


def run_trade_plan(
    forecast_file,
    prices_file,
    asof_date,
    capital,
    exposure_cap,
    execution_mode,
    output_dir,
    month_str=None,
    max_open=None,
    tp_pct=None,
    sl_pct=None,
):
    """
    Call core run_trade_plan.py via subprocess.
    
    Args:
        forecast_file: path to signals_with_gates.parquet
        prices_file: path to ohlcv_daily.parquet
        asof_date: YYYY-MM-DD (T-1 trading day)
        capital: initial capital
        exposure_cap: position cap
        execution_mode: intraday|fast|balanced|conservative
        output_dir: directory for outputs
        month_str: YYYY-MM (extracted from asof_date if None)
        max_open: optional cap on concurrently open trades
        tp_pct: optional TP override (fraction, e.g., 0.016)
        sl_pct: optional SL override (fraction, e.g., 0.01)
    
    Returns:
        path to generated trade_plan.csv or None if failed
    """
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    trade_plan_csv = output_dir / "trade_plan.csv"
    audit_json = output_dir / "audit.json"
    
    if month_str is None:
        month_str = asof_date[:7]  # YYYY-MM
    
    cmd = [
        "python", "scripts/run_trade_plan.py",
        "--forecast", str(forecast_file),
        "--prices", str(prices_file),
        "--out", str(trade_plan_csv),
        "--month", month_str,
        "--capital", str(capital),
        "--exposure-cap", str(exposure_cap),
        "--execution-mode", execution_mode,
        "--asof-date", asof_date,
        "--audit-file", str(audit_json),
    ]

    if tp_pct is not None:
        cmd += ["--tp-pct", str(tp_pct)]
    if sl_pct is not None:
        cmd += ["--sl-pct", str(sl_pct)]

    if max_open is not None:
        cmd += ["--max-open", str(max_open)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] run_trade_plan.py failed for asof_date={asof_date}:")
        print(result.stdout)
        print(result.stderr)
        return None
    
    print(f"  [OK] Trade plan generated for asof_date={asof_date}: {trade_plan_csv}")
    return trade_plan_csv


def validate_trade_plan(trade_plan_csv, expected_asof_date, exposure_cap):
    """
    Validate trade_plan.csv matches expected asof_date and respects exposure cap.
    
    Returns:
        (is_valid, error_message)
    """
    try:
        df = pd.read_csv(trade_plan_csv)
        
        # Check asof_date column exists
        if 'asof_date' not in df.columns:
            return False, "Missing 'asof_date' column"
        
        # Check asof_date matches expected
        unique_dates = df['asof_date'].unique()
        if len(unique_dates) != 1 or unique_dates[0] != expected_asof_date:
            return False, f"asof_date mismatch: expected {expected_asof_date}, got {unique_dates}"
        
        # Check exposure <= cap (with 1% tolerance for float)
        if 'exposure' in df.columns:
            total_exposure = df['exposure'].sum()
            if total_exposure > exposure_cap * 1.01:
                return False, f"exposure {total_exposure:.2f} > cap {exposure_cap}"
        
        return True, None
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def main():
    ap = argparse.ArgumentParser(description="Walk-forward paper sim (monthly)")
    ap.add_argument("--month", required=True, help="Month (YYYY-MM)")
    ap.add_argument("--capital", type=float, default=1000, help="Initial capital")
    ap.add_argument("--exposure-cap", type=float, default=800, help="Exposure cap")
    ap.add_argument("--max-open", type=int, default=None, help="Limit concurrent open positions (passed to run_trade_plan)")
    ap.add_argument("--execution-mode", choices=["intraday", "fast", "balanced", "conservative"], default="balanced")
    ap.add_argument("--max-hold-days", type=int, default=3, help="Max holding period")
    ap.add_argument("--intraday", required=True, help="Path to intraday parquet cache")
    ap.add_argument("--evidence-dir", default="evidence/paper_sep_2025", help="Evidence output directory")
    ap.add_argument("--state-dir", default="paper_state", help="Paper broker state directory")
    ap.add_argument("--forecast", default="data/daily/signals_with_gates.parquet")
    ap.add_argument("--prices", default="data/daily/ohlcv_daily.parquet")
    ap.add_argument("--tickers-file", default=None, help="Path to tickers file (json/txt) to force universe")
    ap.add_argument("--tickers", default=None, help="Comma-separated tickers to force universe")
    ap.add_argument("--tp-sl-choice", default=None, help="Path to tp_sl_choice.json to override TP/SL")
    ap.add_argument("--tp-pct", type=float, default=None, help="Override TP distance as %. e.g., 0.02 for 2%")
    ap.add_argument("--sl-pct", type=float, default=None, help="Override SL distance as %. e.g., 0.012 for 1.2%")
    ap.add_argument("--commission", type=float, default=0.0, help="Fixed commission per trade (round-trip), in dollars")
    ap.add_argument("--slippage-pct", type=float, default=0.0, help="Slippage fraction applied to entry and exit (e.g., 0.0005 for 5bps)")
    
    args = ap.parse_args()

    if args.tickers and args.tickers_file:
        raise SystemExit("Use either --tickers or --tickers-file, not both")

    tickers = []
    if args.tickers_file:
        tickers = load_tickers_from_file(args.tickers_file)
        print(f"[INFO] Forced universe from file ({len(tickers)}): {tickers}")
    elif args.tickers:
        tickers = parse_ticker_list(args.tickers)
        print(f"[INFO] Forced universe from CLI ({len(tickers)}): {tickers}")

    tp_pct = args.tp_pct
    sl_pct = args.sl_pct
    if args.tp_sl_choice:
        choice_path = Path(args.tp_sl_choice)
        choice_data = json.loads(choice_path.read_text())
        final_choice = choice_data.get("final_choice", {})
        tp_pct = final_choice.get("tp_pct", tp_pct)
        sl_pct = final_choice.get("sl_pct", sl_pct)
        print(f"[INFO] TP/SL overridden from {choice_path}: tp_pct={tp_pct}, sl_pct={sl_pct}")

    # Setup
    evidence_base = Path(args.evidence_dir)
    evidence_base.mkdir(parents=True, exist_ok=True)

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    forecast_path = Path(args.forecast)
    forecast_to_use = forecast_path
    if tickers:
        filtered_path = state_dir / f"forecast_filtered_{args.month.replace('-', '')}{forecast_path.suffix}"
        forecast_to_use = filter_forecast_universe(forecast_path, tickers, filtered_path)

    # Load intraday cache
    print(f"[INFO] Loading intraday cache: {args.intraday}")
    intraday_df = pd.read_parquet(args.intraday)
    print(f"  {len(intraday_df)} rows")
    
    # Extract available dates from intraday cache
    intraday_df['dt'] = pd.to_datetime(intraday_df.iloc[:, 0])  # First column is datetime
    available_dates = set(intraday_df['dt'].dt.date.unique())
    print(f"  Available 15m data dates: {sorted(available_dates)}")
    
    # Walk-forward
    all_trades = []
    month_pnl = 0.0
    
    print(f"\n[WALK-FORWARD] Month: {args.month}, Mode: {args.execution_mode}")
    
    weekdays = get_weekday_range(args.month)
    # Filter to only days with intraday data
    weekdays_with_data = [d for d in weekdays if d.date() in available_dates]
    
    print(f"  Total trading days in month: {len(weekdays)}")
    print(f"  Days with 15m data: {len(weekdays_with_data)}")
    print(f"  Simulating dates: {[d.strftime('%Y-%m-%d') for d in weekdays_with_data]}")
    
    for trade_date in weekdays_with_data:
        trade_date_str = trade_date.strftime("%Y-%m-%d")
        asof_date = get_asof_date(trade_date)
        
        # Create day directory
        day_dir = evidence_base / trade_date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n[{trade_date_str}] Simulating (asof_date={asof_date})")
        
        # Generate trade plan for this date
        trade_plan_csv = run_trade_plan(
            forecast_to_use, args.prices, asof_date,
            args.capital, args.exposure_cap, args.execution_mode,
            day_dir, month_str=args.month, max_open=args.max_open,
            tp_pct=tp_pct, sl_pct=sl_pct
        )
        
        if trade_plan_csv is None or not trade_plan_csv.exists():
            print(f"  [SKIP] No trade plan generated")
            continue
        
        # Validate plan (optional check - warning only)
        is_valid, error_msg = validate_trade_plan(trade_plan_csv, asof_date, args.exposure_cap)
        if not is_valid:
            print(f"  [WARN] Validation: {error_msg}")
            # Don't stop - continue with simulation
        
        # Load and filter trade plan
        trade_plan = pd.read_csv(trade_plan_csv)
        trade_plan = trade_plan[trade_plan["qty"] > 0]
        
        if trade_plan.empty:
            print(f"  [SKIP] No trades with qty>0")
            continue
        
        # CRITICAL: Override plan's date with actual simulation date
        # (plan may have forecast date, but we simulate on trade_date_str)
        trade_plan["date"] = trade_date_str
        
        # Add audit columns for traceability
        trade_plan["asof_date"] = asof_date  # Data used for this plan (T-1)
        trade_plan["sim_date"] = trade_date_str  # Day being simulated
        
        print(f"  {len(trade_plan)} trades to simulate (date={trade_date_str}, asof_date={asof_date})")
        
        # Simulate intraday
        sim_trades = simulate_trades(
            trade_plan, intraday_df, args.max_hold_days,
            tp_pct=tp_pct, sl_pct=sl_pct,
            commission_per_trade=args.commission, slippage_pct=args.slippage_pct
        )
        
        print(f"  [DEBUG] Simulator returned {len(sim_trades)} trades")
        
        if sim_trades.empty:
            print(f"  [WARN] No sim trades")
            continue
        
        # Save daily sim results
        sim_csv = day_dir / "sim_trades.csv"
        sim_trades.to_csv(sim_csv, index=False)
        
        # Daily stats
        day_pnl = float(sim_trades["pnl"].sum())
        day_tp = len(sim_trades[sim_trades["outcome"] == "TP"])
        day_sl = len(sim_trades[sim_trades["outcome"] == "SL"])
        day_timeout = len(sim_trades[sim_trades["outcome"] == "TIMEOUT"])
        
        print(f"  PnL: ${day_pnl:.2f} | TP: {day_tp}, SL: {day_sl}, TO: {day_timeout}")
        
        # Save day report
        day_report = {
            "date": trade_date_str,
            "asof_date": asof_date,
            "trades": len(sim_trades),
            "pnl": float(day_pnl),
            "tp_count": int(day_tp),
            "sl_count": int(day_sl),
            "timeout_count": int(day_timeout),
            "execution_mode": args.execution_mode,
        }
        
        day_report_json = day_dir / "day_report.json"
        with open(day_report_json, "w") as f:
            json.dump(day_report, f, indent=2)
        
        # Accumulate
        all_trades.append(sim_trades)
        month_pnl += day_pnl
    
    # Month summary
    print(f"\n=== MONTHLY SUMMARY ===")
    print(f"Month: {args.month}")
    print(f"Mode: {args.execution_mode}")
    
    if all_trades:
        all_trades_df = pd.concat(all_trades, ignore_index=True)
        all_trades_csv = evidence_base / "all_trades.csv"
        all_trades_df.to_csv(all_trades_csv, index=False)
        print(f"Total trades: {len(all_trades_df)}")
        
        # Stats
        stats = summary_stats(all_trades_df, args.capital)
        print(f"Total P&L: ${stats['total_pnl']:.2f}")
        print(f"Final Equity: ${stats['final_equity']:.2f}")
        print(f"Win Rate: {stats['win_rate']:.1f}%")
        print(f"TP: {stats['tp_count']}, SL: {stats['sl_count']}, TO: {stats['timeout_count']}")
        print(f"MDD: {stats['mdd_pct']:.2f}%")
        
        # Save summary
        summary = {
            "month": args.month,
            "execution_mode": args.execution_mode,
            "capital": args.capital,
            "exposure_cap": args.exposure_cap,
            **stats,
        }
        
        summary_json = evidence_base / "summary.json"
        with open(summary_json, "w") as f:
            json.dump(summary, f, indent=2)
        
        # Equity curve
        eq_df = equity_curve(all_trades_df, args.capital)
        eq_csv = evidence_base / "equity_curve.csv"
        eq_df.to_csv(eq_csv, index=False)
        
        print(f"\n[OK] Evidence saved to {evidence_base}")
    else:
        print(f"[WARN] No trades executed this month")


if __name__ == "__main__":
    main()
