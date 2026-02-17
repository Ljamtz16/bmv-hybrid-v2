#!/usr/bin/env python3
"""
paper/metrics.py
Calculate equity, drawdown, CAGR from simulated trades.
"""

import pandas as pd
import numpy as np


def equity_curve(trades, initial_cash):
    """
    Build equity curve from trades.
    
    Args:
        trades: DataFrame with exit_time and pnl columns
        initial_cash: initial capital
    
    Returns:
        equity_df: DataFrame with datetime and equity
    """
    if trades.empty:
        return pd.DataFrame({"datetime": [], "equity": []})
    
    trades = trades.sort_values("exit_time").copy()
    trades["cumulative_pnl"] = trades["pnl"].cumsum()
    trades["equity"] = initial_cash + trades["cumulative_pnl"]
    
    equity_df = trades[["exit_time", "equity"]].copy()
    equity_df.columns = ["datetime", "equity"]
    
    return equity_df.reset_index(drop=True)


def max_drawdown(equity_df):
    """
    Calculate max drawdown from equity curve.
    
    Returns:
        dict with mdd_pct, peak_datetime, trough_datetime
    """
    if equity_df.empty or equity_df["equity"].empty:
        return {"mdd_pct": 0.0, "peak_datetime": None, "trough_datetime": None}
    
    equity = equity_df["equity"].values
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    
    mdd_idx = np.argmax(drawdown)
    mdd_pct = float(drawdown[mdd_idx]) * 100
    
    peak_idx = np.argmax(peak[:mdd_idx + 1])
    peak_dt = equity_df.iloc[peak_idx]["datetime"] if peak_idx < len(equity_df) else None
    trough_dt = equity_df.iloc[mdd_idx]["datetime"] if mdd_idx < len(equity_df) else None
    
    return {
        "mdd_pct": mdd_pct,
        "peak_datetime": peak_dt,
        "trough_datetime": trough_dt,
    }


def cagr(initial_capital, final_capital, days):
    """
    Calculate CAGR (annualized return).
    
    Returns:
        dict with monthly_cagr and annualized_cagr
    """
    if days <= 0 or initial_capital <= 0:
        return {"monthly_cagr": 0.0, "annualized_cagr": 0.0}
    
    years = days / 365.0
    if years <= 0:
        return {"monthly_cagr": 0.0, "annualized_cagr": 0.0}
    
    annual_cagr = (final_capital / initial_capital) ** (1.0 / years) - 1.0
    monthly_cagr = (final_capital / initial_capital) ** (1.0 / (days / 30.0)) - 1.0
    
    return {
        "monthly_cagr": float(monthly_cagr),
        "annualized_cagr": float(annual_cagr),
    }


def summary_stats(trades, initial_cash):
    """
    Compute summary statistics from trades.
    
    Returns:
        dict with aggregate stats
    """
    if trades.empty:
        return {
            "total_trades": 0,
            "total_pnl": 0.0,
            "realized_pnl": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_hold_hours": 0.0,
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "mdd_pct": 0.0,
            "final_equity": initial_cash,
        }
    
    total_pnl = float(trades["pnl"].sum())
    final_equity = initial_cash + total_pnl
    
    # Win rate
    tp_trades = trades[trades["outcome"] == "TP"]
    sl_trades = trades[trades["outcome"] == "SL"]
    timeout_trades = trades[trades["outcome"] == "TIMEOUT"]
    
    tp_count = len(tp_trades)
    sl_count = len(sl_trades)
    timeout_count = len(timeout_trades)
    
    # Wins = TP + some timeouts (if pnl > 0)
    wins = len(trades[trades["pnl"] > 0])
    total = len(trades)
    win_rate = (wins / total * 100) if total > 0 else 0.0
    
    # Avg win/loss
    winning_trades = trades[trades["pnl"] > 0]
    losing_trades = trades[trades["pnl"] < 0]
    avg_win = float(winning_trades["pnl"].mean()) if len(winning_trades) > 0 else 0.0
    avg_loss = float(losing_trades["pnl"].mean()) if len(losing_trades) > 0 else 0.0
    
    # Avg hold
    avg_hold = float(trades["hold_hours"].mean())
    
    # Dates
    if "exit_time" in trades.columns:
        date_range = (trades["exit_time"].max() - trades["exit_time"].min()).days
    else:
        date_range = 0
    
    # MDD
    eq_df = equity_curve(trades, initial_cash)
    mdd_info = max_drawdown(eq_df)
    
    return {
        "total_trades": int(total),
        "total_pnl": float(total_pnl),
        "final_equity": float(final_equity),
        "win_rate": float(win_rate),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "avg_hold_hours": float(avg_hold),
        "tp_count": int(tp_count),
        "sl_count": int(sl_count),
        "timeout_count": int(timeout_count),
        "mdd_pct": float(mdd_info["mdd_pct"]),
        "date_range_days": int(date_range),
    }
