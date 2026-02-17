#!/usr/bin/env python3
"""
generate_intraday_trades_csv.py
Generate intraday trades CSV for 2022-2025 using forecast signals and 15m data.
Direct simulation (no subprocess overhead).
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime, timedelta
import sys

# Add paper module to path
sys.path.insert(0, str(Path(__file__).parent / "paper"))


def simulate_trades_simple(forecast_df, prices_15m_df, capital, tp_pct, sl_pct, prob_win_threshold=0.55, max_hold_days=3):
    """
    Simple direct intraday simulator without subprocess.
    
    Args:
        forecast_df: DataFrame with ticker, date, prob_win
        prices_15m_df: DataFrame with datetime, ticker, open, high, low, close, volume
        capital: Initial capital
        tp_pct: Take profit percentage (0.016 = 1.6%)
        sl_pct: Stop loss percentage (0.01 = 1%)
        prob_win_threshold: Minimum prob_win to accept signal (default 0.55)
        max_hold_days: Max holding period in trading days
    
    Returns:
        trades: List of dicts with trade results
    """
    
    trades = []
    equity = capital
    exposure = 0
    position_size = capital * 0.1  # 10% per trade
    
    # Normalize 15m data
    prices_15m_df['datetime'] = pd.to_datetime(prices_15m_df.iloc[:, 0])
    prices_15m_df['date_only'] = prices_15m_df['datetime'].dt.date
    prices_15m_df = prices_15m_df.sort_values('datetime')
    
    # Group 15m data by ticker and date
    prices_by_ticker_date = {}
    for ticker in prices_15m_df['ticker'].unique():
        ticker_data = prices_15m_df[prices_15m_df['ticker'] == ticker]
        for date in ticker_data['date_only'].unique():
            key = (str(ticker), str(date))
            prices_by_ticker_date[key] = ticker_data[ticker_data['date_only'] == date]
    
    print(f"[SIM] Loaded price data for {len(prices_by_ticker_date)} ticker-dates")
    
    # Process each forecast signal
    for idx, row in forecast_df.iterrows():
        if idx % 1000 == 0:
            print(f"  Processing trade {idx}/{len(forecast_df)}...")
        
        ticker = str(row['ticker']).upper()
        trade_date = pd.to_datetime(row['date']).date()
        prob_win = row.get('prob_win', 0.5)
        
        # Filter by prob_win threshold
        if prob_win < prob_win_threshold:
            continue
        
        # Determine side (only BUY signals above threshold)
        side = 'BUY'
        
        # Get entry price (opening price of the day in 15m data)
        key = (ticker, str(trade_date))
        if key not in prices_by_ticker_date:
            continue
        
        day_data = prices_by_ticker_date[key]
        if day_data.empty:
            continue
        
        # Get first 15m candle as entry
        first_candle = day_data.iloc[0]
        entry_time = first_candle['datetime']
        entry_price = float(first_candle['open'])
        
        # Calculate TP/SL
        if side == 'BUY':
            tp_price = entry_price * (1 + tp_pct)
            sl_price = entry_price * (1 - sl_pct)
        else:
            tp_price = entry_price * (1 - tp_pct)
            sl_price = entry_price * (1 + sl_pct)
        
        # Simulate holding through day
        qty = position_size / entry_price
        exit_price = entry_price
        exit_time = entry_time
        exit_reason = 'TIMEOUT'
        pnl = 0
        
        # Check each candle in the day
        for candle_idx, candle in day_data.iterrows():
            high = float(candle['high'])
            low = float(candle['low'])
            close = float(candle['close'])
            candle_time = candle['datetime']
            
            if side == 'BUY':
                # Check TP
                if high >= tp_price:
                    exit_price = tp_price
                    exit_time = candle_time
                    exit_reason = 'TP'
                    break
                # Check SL
                if low <= sl_price:
                    exit_price = sl_price
                    exit_time = candle_time
                    exit_reason = 'SL'
                    break
                # Update last close
                exit_price = close
            else:  # SELL
                # Check TP
                if low <= tp_price:
                    exit_price = tp_price
                    exit_time = candle_time
                    exit_reason = 'TP'
                    break
                # Check SL
                if high >= sl_price:
                    exit_price = sl_price
                    exit_time = candle_time
                    exit_reason = 'SL'
                    break
                # Update last close
                exit_price = close
        
        # Calculate PnL
        if side == 'BUY':
            pnl = (exit_price - entry_price) * qty
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl = (entry_price - exit_price) * qty
            pnl_pct = (entry_price - exit_price) / entry_price
        
        equity += pnl
        
        # Record trade
        trade = {
            'ticker': ticker,
            'side': side,
            'entry_time': entry_time,
            'entry_price': entry_price,
            'exit_time': exit_time,
            'exit_price': exit_price,
            'outcome': 'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'BREAK',
            'exit_reason': exit_reason,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'hold_hours': (exit_time - entry_time).total_seconds() / 3600,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'qty': qty,
            'trade_date': trade_date,
            'tp_distance_pct': tp_pct if side == 'BUY' else tp_pct,
            'sl_distance_pct': sl_pct,
        }
        
        trades.append(trade)
    
    print(f"[RESULT] {len(trades)} trades executed")
    return trades, equity


def main():
    import argparse
    
    ap = argparse.ArgumentParser(description="Generate intraday trades 2022-2025")
    ap.add_argument("--capital", type=float, default=600, help="Initial capital")
    ap.add_argument("--tp-pct", type=float, required=True, help="TP % (e.g., 0.016)")
    ap.add_argument("--sl-pct", type=float, required=True, help="SL % (e.g., 0.01)")
    ap.add_argument("--intraday", required=True, help="Intraday 15m parquet")
    ap.add_argument("--forecast", default="data/daily/signals_with_gates.parquet")
    ap.add_argument("--output-dir", required=True, help="Output directory")
    ap.add_argument("--start-date", default="2022-01-01")
    ap.add_argument("--end-date", default="2025-12-31")
    ap.add_argument("--prob-win-threshold", type=float, default=0.55, help="Min prob_win to accept signal (default: 0.55)")
    
    args = ap.parse_args()
    
    print(f"\n[GEN] Intraday Trades CSV 2022-2025")
    print(f"  Capital: ${args.capital}")
    print(f"  TP: {args.tp_pct*100:.2f}% | SL: {args.sl_pct*100:.2f}%")
    print(f"  Prob Win Threshold: {args.prob_win_threshold:.2f}")
    print(f"  Output: {args.output_dir}")
    
    # Load data
    print(f"\n[LOAD] Data...")
    intraday_df = pd.read_parquet(args.intraday)
    forecast_df = pd.read_parquet(args.forecast)
    
    print(f"  Intraday: {len(intraday_df)} rows")
    print(f"  Forecast: {len(forecast_df)} rows")
    
    # Filter forecast by date
    if 'date' in forecast_df.columns:
        forecast_df['date'] = pd.to_datetime(forecast_df['date'])
    else:
        forecast_df['date'] = pd.to_datetime(forecast_df.get('date_only', forecast_df.get('asof_date')))
    
    start_dt = pd.to_datetime(args.start_date)
    end_dt = pd.to_datetime(args.end_date)
    forecast_df = forecast_df[(forecast_df['date'] >= start_dt) & (forecast_df['date'] <= end_dt)].copy()
    print(f"  Forecast (filtered): {len(forecast_df)} rows")
    
    # Simulate
    print(f"\n[SIM] Simulating trades...")
    trades, final_equity = simulate_trades_simple(
        forecast_df,
        intraday_df,
        args.capital,
        args.tp_pct,
        args.sl_pct,
        prob_win_threshold=args.prob_win_threshold,
        max_hold_days=3
    )
    
    if not trades:
        print("[WARN] No trades generated!")
        return
    
    # Convert to DataFrame
    trades_df = pd.DataFrame(trades)
    
    # Save results
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save trades CSV
    trades_file = output_path / "all_trades.csv"
    trades_df.to_csv(trades_file, index=False)
    print(f"\n[OK] Trades saved → {trades_file}")
    
    # Generate summary
    pnl_col = 'pnl'
    summary = {
        "total_trades": len(trades_df),
        "total_pnl": float(trades_df[pnl_col].sum()),
        "final_equity": float(final_equity),
        "win_count": int((trades_df[pnl_col] > 0).sum()),
        "loss_count": int((trades_df[pnl_col] < 0).sum()),
        "win_rate_pct": float((trades_df[pnl_col] > 0).sum() / len(trades_df) * 100) if len(trades_df) > 0 else 0,
        "gross_profit": float(trades_df[trades_df[pnl_col] > 0][pnl_col].sum()),
        "gross_loss": float(abs(trades_df[trades_df[pnl_col] < 0][pnl_col].sum())),
    }
    
    if summary["gross_loss"] > 0:
        summary["profit_factor"] = summary["gross_profit"] / summary["gross_loss"]
    else:
        summary["profit_factor"] = float('inf')
    
    summary_file = output_path / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n[SUMMARY]")
    print(f"  Trades: {summary['total_trades']}")
    print(f"  P&L: ${summary['total_pnl']:.2f}")
    print(f"  Final Equity: ${summary['final_equity']:.2f}")
    print(f"  Win Rate: {summary['win_rate_pct']:.1f}%")
    print(f"  Profit Factor: {summary['profit_factor']:.2f}x" if summary['profit_factor'] != float('inf') else "  Profit Factor: inf")
    print(f"\n  Summary → {summary_file}")
    
    print("\n[DONE]")


if __name__ == "__main__":
    main()
