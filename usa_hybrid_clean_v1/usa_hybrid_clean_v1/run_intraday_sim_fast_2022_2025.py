#!/usr/bin/env python3
"""
run_intraday_sim_fast_2022_2025.py
Fast intraday simulation for 2022-2025 without subprocess overhead.
Directly generates trades and consolidates.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime, timedelta
import sys

# Add paper module to path
sys.path.insert(0, str(Path(__file__).parent / "paper"))

from intraday_simulator import simulate_trades
from metrics import summary_stats, equity_curve


def main():
    import argparse
    
    ap = argparse.ArgumentParser(description="Fast intraday sim 2022-2025")
    ap.add_argument("--capital", type=float, default=600, help="Initial capital")
    ap.add_argument("--tp-pct", type=float, required=True, help="TP %")
    ap.add_argument("--sl-pct", type=float, required=True, help="SL %")
    ap.add_argument("--intraday", required=True, help="Intraday parquet path")
    ap.add_argument("--evidence-dir", default="evidence/paper_2022_2025_intraday", help="Output dir")
    ap.add_argument("--start-date", default="2022-01-01")
    ap.add_argument("--end-date", default="2025-12-31")
    ap.add_argument("--forecast", default="data/daily/signals_with_gates.parquet")
    ap.add_argument("--prices", default="data/daily/ohlcv_daily.parquet")
    
    args = ap.parse_args()
    
    print(f"\n[FAST SIM] 2022-2025 Intraday")
    print(f"  Capital: ${args.capital}")
    print(f"  TP: {args.tp_pct*100:.1f}% | SL: {args.sl_pct*100:.1f}%")
    print(f"  Output: {args.evidence_dir}")
    
    # Load intraday 15m data
    print(f"\n[LOAD] Intraday 15m cache...")
    intraday_df = pd.read_parquet(args.intraday)
    print(f"  {len(intraday_df)} rows loaded")
    
    # Get date range from intraday
    intraday_df['datetime'] = pd.to_datetime(intraday_df.iloc[:, 0]) if not isinstance(intraday_df.iloc[0, 0], (pd.Timestamp, type(pd.Timestamp.now()))) else intraday_df.iloc[:, 0]
    available_dates = sorted(intraday_df['datetime'].dt.date.unique())
    print(f"  Date range: {available_dates[0]} to {available_dates[-1]}")
    
    # Load forecast
    print(f"\n[LOAD] Forecast...")
    forecast_df = pd.read_parquet(args.forecast) if Path(args.forecast).suffix == ".parquet" else pd.read_csv(args.forecast)
    forecast_df['date'] = pd.to_datetime(forecast_df.get('date', forecast_df.get('date_only', forecast_df.get('asof_date'))))
    print(f"  {len(forecast_df)} rows")
    
    # Load prices (daily OHLCV for daily bars)
    print(f"\n[LOAD] Daily prices...")
    prices_df = pd.read_parquet(args.prices) if Path(args.prices).suffix == ".parquet" else pd.read_csv(args.prices)
    print(f"  {len(prices_df)} rows")
    
    # Generate a simple trade plan from forecast
    # For now, use the forecast directly with some basic filtering
    start_date = pd.to_datetime(args.start_date).date()
    end_date = pd.to_datetime(args.end_date).date()
    
    forecast_df = forecast_df[(forecast_df['date'].dt.date >= start_date) & (forecast_df['date'].dt.date <= end_date)].copy()
    print(f"\n[PLAN] Filtered forecast: {len(forecast_df)} rows for {start_date} to {end_date}")
    
    # Create trade plan from forecast (simple: BUY if prob_win > 0.5)
    if 'prob_win' not in forecast_df.columns:
        print("[WARN] No prob_win column, using forecast as-is")
        forecast_df['side'] = 'BUY'
    else:
        forecast_df['side'] = forecast_df['prob_win'].apply(lambda x: 'BUY' if x > 0.5 else 'SELL')
    
    # Prepare trade plan
    trade_plan = forecast_df[['ticker', 'side', 'date']].copy()
    trade_plan.columns = ['ticker', 'side', 'date']
    trade_plan['entry'] = 100.0  # Placeholder, will be filled by simulator
    trade_plan['tp_price'] = 100.0 * (1 + args.tp_pct)  # Placeholder
    trade_plan['sl_price'] = 100.0 * (1 - args.sl_pct)  # Placeholder
    trade_plan['qty'] = 1
    trade_plan['date'] = trade_plan['date'].dt.strftime('%Y-%m-%d')
    
    print(f"[PLAN] Generated trade plan: {len(trade_plan)} trades")
    
    # Simulate
    print(f"\n[SIM] Running simulation...")
    try:
        sim_trades = simulate_trades(
            trade_plan,
            intraday_df,
            max_hold_days=3,
            tp_pct=args.tp_pct,
            sl_pct=args.sl_pct,
            commission_per_trade=0.0,
            slippage_pct=0.0
        )
        print(f"  {len(sim_trades)} trades simulated")
    except Exception as e:
        print(f"[ERROR] Simulation failed: {e}")
        sim_trades = pd.DataFrame()
    
    # Save results
    output_dir = Path(args.evidence_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not sim_trades.empty:
        # Save trades
        trades_file = output_dir / "all_trades.csv"
        sim_trades.to_csv(trades_file, index=False)
        print(f"\n[OK] Trades saved → {trades_file}")
        
        # Generate summary
        if 'pnl' in sim_trades.columns:
            pnl_col = 'pnl'
        elif 'pnl_pct' in sim_trades.columns:
            pnl_col = 'pnl_pct'
        else:
            pnl_col = sim_trades.columns[-1]  # Last column
        
        summary = {
            "total_trades": len(sim_trades),
            "total_pnl": float(sim_trades[pnl_col].sum()),
            "win_count": int((sim_trades[pnl_col] > 0).sum()),
            "loss_count": int((sim_trades[pnl_col] < 0).sum()),
            "win_rate_pct": float((sim_trades[pnl_col] > 0).sum() / len(sim_trades) * 100),
        }
        
        summary_file = output_dir / "summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n[SUMMARY]")
        print(f"  Trades: {summary['total_trades']}")
        print(f"  P&L: ${summary['total_pnl']:.2f}")
        print(f"  Win Rate: {summary['win_rate_pct']:.1f}%")
        print(f"  Summary → {summary_file}")
    else:
        print("[WARN] No trades generated")
    
    print("\n[DONE]")


if __name__ == "__main__":
    main()
