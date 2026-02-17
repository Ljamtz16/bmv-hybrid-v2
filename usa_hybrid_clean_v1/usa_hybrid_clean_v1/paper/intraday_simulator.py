#!/usr/bin/env python3
"""
paper/intraday_simulator.py
Simulate paper trades intraday (hour-by-hour) using cached OHLC candles.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _reshape_wide_to_long(df_wide):
    """
    Reshape wide-format intraday cache to long format.
    Wide: datetime | ticker | (open, AMD) | (open, CVX) | ...
    Long: datetime | ticker | open | high | low | close | volume
    """
    # Already in long format
    if 'open' in df_wide.columns and 'high' in df_wide.columns:
        return df_wide
    
    # Parse column names if they're stringified tuples
    if isinstance(df_wide.columns[0], str) and df_wide.columns[0].startswith("('"):
        import ast
        cols = [ast.literal_eval(col) if col.startswith("('") else col for col in df_wide.columns]
    elif isinstance(df_wide.columns[0], tuple):
        cols = df_wide.columns
    else:
        cols = df_wide.columns
    
    # Extract datetime column (first one)
    df_wide.columns = cols
    dt_col = [c for c in cols if isinstance(c, tuple) and c[0] == 'datetime'][0]
    ticker_col = [c for c in cols if isinstance(c, tuple) and c[0] == 'ticker'][0]
    
    # Get unique tickers from column names
    tickers = set()
    for col in cols:
        if isinstance(col, tuple) and len(col) == 2 and col[0] in ['open', 'high', 'low', 'close', 'volume']:
            tickers.add(col[1])
    
    # Melt to long format
    dfs = []
    for ticker in tickers:
        ticker_df = df_wide[[dt_col]].copy()
        ticker_df['ticker'] = ticker
        ticker_df['datetime'] = df_wide[dt_col]
        
        for field in ['open', 'high', 'low', 'close', 'volume']:
            col_name = (field, ticker)
            if col_name in df_wide.columns:
                ticker_df[field] = df_wide[col_name]
        
        # Drop rows where all OHLCV are NaN
        ticker_df = ticker_df.dropna(subset=['open', 'high', 'low', 'close'], how='all')
        dfs.append(ticker_df)
    
    return pd.concat(dfs, ignore_index=True)


def simulate_trades(trade_plan, intraday_df, max_hold_days=3, tp_pct=None, sl_pct=None, commission_per_trade: float = 0.0, slippage_pct: float = 0.0):
    """
    Simulate trades intraday using cached candles.
    
    Args:
        trade_plan: DataFrame with columns [ticker, side, entry, tp_price, sl_price, qty, date]
        intraday_df: DataFrame with columns [datetime, ticker, open, high, low, close, volume]
        max_hold_days: max TRADING SESSIONS to hold (not calendar days)
                       max_hold_days=2 means:
                         - Day 0: from entry until EOD (market close)
                         - Day 1: next trading day until EOD
                         - TIMEOUT forced at close of Day 1 if no TP/SL hit
        tp_pct: optional TP distance % (overrides plan values). e.g., 0.02 for 2%
        sl_pct: optional SL distance % (overrides plan values). e.g., 0.012 for 1.2%
        commission_per_trade: fixed dollar commission per trade (round-trip)
        slippage_pct: percentage slippage on entry/exit (e.g., 0.0005 = 0.05%)
    
    Returns:
        sim_trades: DataFrame with trading results
    """
    
    # Reshape if needed (wide → long)
    df = _reshape_wide_to_long(intraday_df)
    
    trades = []
    
    for idx, plan_row in trade_plan.iterrows():
        ticker = plan_row["ticker"]
        side = str(plan_row["side"]).upper()
        entry_price = float(plan_row["entry"])
        tp_price = float(plan_row["tp_price"])
        sl_price = float(plan_row["sl_price"])
        qty = float(plan_row.get("qty", 0) or 0)
        # Use 'date' column (simulation date), not 'asof_date'
        trade_date_str = str(plan_row["date"])
        
        if qty <= 0:
            continue
        
        # Filter intraday for this ticker
        ticker_data = df[df["ticker"] == ticker].copy()
        if ticker_data.empty:
            trades.append({
                "ticker": ticker,
                "side": side,
                "entry_time": None,
                "entry_price": entry_price,
                "exit_time": None,
                "exit_price": None,
                "outcome": "NO_DATA",
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "hold_hours": 0,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "qty": qty,
                "trade_date": trade_date_str,
            })
            continue
        
        # Rename 'timestamp' to 'datetime' if needed for compatibility
        if "timestamp" in ticker_data.columns and "datetime" not in ticker_data.columns:
            ticker_data = ticker_data.rename(columns={"timestamp": "datetime"})
        
        ticker_data = ticker_data.sort_values("datetime").reset_index(drop=True)
        
        # Find entry: first candle on/after trade_date (market open)
        trade_dt = pd.to_datetime(trade_date_str)
        # Make timezone-aware to match intraday cache (UTC)
        if trade_dt.tz is None and hasattr(ticker_data["datetime"].iloc[0], 'tz') and ticker_data["datetime"].iloc[0].tz is not None:
            trade_dt = trade_dt.tz_localize('UTC')
        
        entry_data = ticker_data[ticker_data["datetime"] >= trade_dt]
        
        if entry_data.empty:
            trades.append({
                "ticker": ticker,
                "side": side,
                "entry_time": None,
                "entry_price": entry_price,
                "exit_time": None,
                "exit_price": None,
                "outcome": "NO_ENTRY",
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "hold_hours": 0,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "qty": qty,
                "trade_date": trade_date_str,
            })
            continue
        
        entry_idx = entry_data.index[0]
        entry_time = ticker_data.loc[entry_idx, "datetime"]
        
        # CRITICAL FIX: Use actual OPEN price of first candle as entry
        # Plan's entry_price comes from asof_date (T-1 close), not sim_date open
        actual_entry_price = float(ticker_data.loc[entry_idx, "open"])
        # Apply slippage on entry (worsen price)
        if slippage_pct and slippage_pct > 0:
            if side == "BUY":
                actual_entry_price *= (1 + slippage_pct)
            else:
                actual_entry_price *= (1 - slippage_pct)
        
        # If tp_pct/sl_pct provided, use them instead of plan values (parameter override)
        if tp_pct is not None and sl_pct is not None:
            if side == "BUY":
                tp_price = actual_entry_price * (1 + tp_pct)
                sl_price = actual_entry_price * (1 - sl_pct)
            else:  # SELL
                tp_price = actual_entry_price * (1 - tp_pct)
                sl_price = actual_entry_price * (1 + sl_pct)
        else:
            # Recalculate TP/SL based on actual entry, preserving % distances from plan
            plan_tp_distance_pct = (tp_price - entry_price) / entry_price if side == "BUY" else (entry_price - tp_price) / entry_price
            plan_sl_distance_pct = (entry_price - sl_price) / entry_price if side == "BUY" else (sl_price - entry_price) / entry_price
            
            if side == "BUY":
                tp_price = actual_entry_price * (1 + plan_tp_distance_pct)
                sl_price = actual_entry_price * (1 - plan_sl_distance_pct)
            else:  # SELL
                tp_price = actual_entry_price * (1 - plan_tp_distance_pct)
                sl_price = actual_entry_price * (1 + plan_sl_distance_pct)
        
        # Update entry_price to actual market price
        entry_price = actual_entry_price
        
        # Calculate max hold window: max_hold_days TRADING sessions
        # Day 0: from entry until EOD (market close)
        # Day 1...N-1: subsequent full trading days
        # TIMEOUT: at close of Day (max_hold_days - 1)
        #
        # Strategy: Find unique trading dates in data, locate entry date, 
        # then find Nth date forward (0-indexed: max_hold_days-1 offset)
        ticker_data["date_only"] = pd.to_datetime(ticker_data["datetime"]).dt.date
        unique_trade_dates = sorted(ticker_data["date_only"].unique())
        
        entry_date = pd.to_datetime(entry_time).date()
        if entry_date not in unique_trade_dates:
            # Entry date not in available data → use next available
            entry_date = min([d for d in unique_trade_dates if d >= entry_date], default=None)
            if entry_date is None:
                # No future data → skip trade
                trades.append({
                    "ticker": ticker,
                    "side": side,
                    "entry_time": entry_time,
                    "entry_price": entry_price,
                    "exit_time": None,
                    "exit_price": None,
                    "outcome": "NO_DATA_POST_ENTRY",
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                    "hold_hours": 0,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "qty": qty,
                    "trade_date": trade_date_str,
                })
                continue
        
        entry_date_idx = unique_trade_dates.index(entry_date)
        # max_hold_days=2 → hold until end of Day 1 (entry_date_idx + 1)
        timeout_date_idx = entry_date_idx + (max_hold_days - 1)
        
        if timeout_date_idx >= len(unique_trade_dates):
            # Not enough data to complete hold window → force timeout at last available date
            timeout_date = unique_trade_dates[-1]
        else:
            timeout_date = unique_trade_dates[timeout_date_idx]
        
        # Get last candle of timeout_date (EOD close)
        eod_candles = ticker_data[ticker_data["date_only"] == timeout_date]
        if eod_candles.empty:
            # Should not happen if logic correct, but fallback
            timeout_datetime = pd.Timestamp(timeout_date) + timedelta(hours=20)  # 20:00 UTC = 16:00 ET (market close)
        else:
            timeout_datetime = eod_candles["datetime"].max()
        
        # Simulate candle-by-candle within hold window
        exit_time = None
        exit_price = None
        outcome = "TIMEOUT"
        
        # Track MFE/MAE (Max Favorable/Adverse Excursion)
        max_favorable = 0.0  # Best unrealized profit during trade
        max_adverse = 0.0    # Worst unrealized loss during trade
        
        for candle_idx in range(entry_idx, len(ticker_data)):
            candle = ticker_data.iloc[candle_idx]
            candle_dt = candle["datetime"]
            candle_date = pd.to_datetime(candle_dt).date()
            
            # Stop if beyond timeout date
            if candle_date > timeout_date:
                break
            
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
            
            # Track MFE/MAE
            if side == "BUY":
                favorable_move = (high - entry_price) / entry_price
                adverse_move = (low - entry_price) / entry_price
                max_favorable = max(max_favorable, favorable_move)
                max_adverse = min(max_adverse, adverse_move)
            else:  # SELL
                favorable_move = (entry_price - low) / entry_price
                adverse_move = (entry_price - high) / entry_price
                max_favorable = max(max_favorable, favorable_move)
                max_adverse = min(max_adverse, adverse_move)
            
            # Check TP/SL
            if side == "BUY":
                # Check SL first (conservative)
                if low <= sl_price:
                    exit_price = sl_price
                    exit_time = candle_dt
                    outcome = "SL"
                    break
                # Then check TP
                elif high >= tp_price:
                    exit_price = tp_price
                    exit_time = candle_dt
                    outcome = "TP"
                    break
            else:  # SELL
                if high >= sl_price:
                    exit_price = sl_price
                    exit_time = candle_dt
                    outcome = "SL"
                    break
                elif low <= tp_price:
                    exit_price = tp_price
                    exit_time = candle_dt
                    outcome = "TP"
                    break
            
            # If we reached timeout_date EOD and no exit yet → force TIMEOUT at close
            if candle_date == timeout_date and candle_dt == timeout_datetime:
                exit_price = close
                exit_time = candle_dt
                outcome = "TIMEOUT"
                break
        
        # If loop ended without exit (should not happen with correct logic), force timeout at EOD
        if exit_time is None:
            eod_final = ticker_data[ticker_data["date_only"] == timeout_date]
            if not eod_final.empty:
                last_candle_eod = eod_final.iloc[-1]
                exit_time = last_candle_eod["datetime"]
                exit_price = float(last_candle_eod["close"])
                outcome = "TIMEOUT"
            else:
                # Fallback: no data for timeout date → skip trade
                trades.append({
                    "ticker": ticker,
                    "side": side,
                    "entry_time": entry_time,
                    "entry_price": entry_price,
                    "exit_time": None,
                    "exit_price": None,
                    "outcome": "NO_DATA_TIMEOUT",
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                    "hold_hours": 0,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "qty": qty,
                    "trade_date": trade_date_str,
                })
                continue
        
        # Calculate PnL
        # Apply slippage on exit
        if slippage_pct and slippage_pct > 0:
            if side == "BUY":
                exit_price *= (1 - slippage_pct)
            else:
                exit_price *= (1 + slippage_pct)

        if side == "BUY":
            pnl = (exit_price - entry_price) * qty
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl = (entry_price - exit_price) * qty
            pnl_pct = (entry_price - exit_price) / entry_price

        # Commission (fixed per trade, round-trip)
        if commission_per_trade and commission_per_trade > 0:
            pnl -= commission_per_trade
        
        hold_hours = (exit_time - entry_time).total_seconds() / 3600 if exit_time else 0
        
        # Calculate distance to TP/SL
        if side == "BUY":
            tp_distance_pct = (tp_price - entry_price) / entry_price
            sl_distance_pct = (entry_price - sl_price) / entry_price
        else:
            tp_distance_pct = (entry_price - tp_price) / entry_price
            sl_distance_pct = (sl_price - entry_price) / entry_price
        
        trades.append({
            "ticker": ticker,
            "side": side,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "outcome": outcome,
            "exit_reason": outcome,  # Alias for clarity
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "hold_hours": hold_hours,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "qty": qty,
            "trade_date": trade_date_str,
            "tp_distance_pct": tp_distance_pct,
            "sl_distance_pct": sl_distance_pct,
            "mfe_pct": max_favorable,  # Max Favorable Excursion
            "mae_pct": max_adverse,    # Max Adverse Excursion
            "commission": commission_per_trade,
            "slippage_pct": slippage_pct,
        })
    
    return pd.DataFrame(trades)
