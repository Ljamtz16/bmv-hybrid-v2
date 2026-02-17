#!/usr/bin/env python3
"""
backtest_hybrid_gate_full.py
Backtest full OOS window using hybrid gate tickers (PFE, CVX, AMD, XOM)

Window: 2024-02-21 to 2026-01-15 (complete forecast range)
TP: 1.6%, SL: 1.0%, max_hold: 2 days
Capital: $1000, Exposure per trade: ~$200 (5 positions max)
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# ============================================================================
# CONFIG
# ============================================================================

INTRADAY_FILE = "C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet"
FORECAST_FILE = "data/daily/forecast_prob_win.parquet"
GATE_FILE = "evidence/hybrid_gate_20260115/hybrid_gate.json"

TP_PCT = 0.016  # 1.6%
SL_PCT = 0.010  # 1.0%
MAX_HOLD_DAYS = 2
CAPITAL = 1000.0
MAX_POSITIONS = 5
COMMISSION = 0.0
SLIPPAGE_PCT = 0.0001

START_DATE = "2024-02-21"
END_DATE = "2026-01-15"

# ============================================================================
# LOAD DATA
# ============================================================================

def load_intraday():
    """Load intraday 15m data."""
    df = pd.read_parquet(INTRADAY_FILE)
    
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], utc=False)
    elif df.columns[0] in ['timestamp', 'datetime']:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    else:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    
    if df['datetime'].dt.tz is not None:
        df['datetime'] = df['datetime'].dt.tz_localize(None)
    
    start = pd.to_datetime(START_DATE)
    end = pd.to_datetime(END_DATE)
    df = df[(df['datetime'] >= start) & (df['datetime'] <= end)].copy()
    df = df.sort_values('datetime').reset_index(drop=True)
    
    return df

def load_gate_selection():
    """Load hybrid gate selection and MC metrics."""
    with open(GATE_FILE) as f:
        data = json.load(f)
    
    selected_tickers = data['selected_tickers']
    
    # Extract MC metrics for each ticker
    mc_metrics = {}
    for rank_entry in data['ranking']:
        ticker = rank_entry['ticker']
        if ticker in selected_tickers:
            mc_metrics[ticker] = {
                'mc_score': rank_entry['mc_score'],
                'mc_normalized': rank_entry['mc_normalized'],
                'ev': rank_entry['mc_metrics']['ev'],
                'tp_rate': rank_entry['mc_metrics']['tp_rate'],
                'hybrid_score': rank_entry['hybrid_score']
            }
    
    return selected_tickers, mc_metrics

def load_forecast():
    """Load forecast prob_win."""
    df = pd.read_parquet(FORECAST_FILE)
    
    # Normalize date column
    if 'date' not in df.columns:
        for col in ['Date', 'forecast_date', 'asof_date', 'datetime']:
            if col in df.columns:
                df['date'] = pd.to_datetime(df[col])
                break
    else:
        df['date'] = pd.to_datetime(df['date'])
    
    start = pd.to_datetime(START_DATE)
    end = pd.to_datetime(END_DATE)
    df = df[(df['date'] >= start) & (df['date'] <= end)].copy()
    
    return df[['ticker', 'date', 'prob_win']].copy()

# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class Trade:
    def __init__(self, ticker: str, entry_date: pd.Timestamp, entry_price: float, 
                 tp_price: float, sl_price: float, max_hold_bars: int, position_size: float):
        self.ticker = ticker
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.max_hold_bars = max_hold_bars
        self.position_size = position_size
        
        self.exit_date = None
        self.exit_price = None
        self.exit_reason = None  # 'TP', 'SL', 'TO' (timeout)
        self.pnl = None
        self.pnl_pct = None

def run_backtest(selected_tickers: List[str], mc_metrics: Dict, intraday_df: pd.DataFrame, forecast_df: pd.DataFrame) -> Dict:
    """Run full backtest with MC-weighted position sizing."""
    
    print("\n" + "="*70)
    print("🎯 HYBRID GATE BACKTEST - FULL OOS WINDOW")
    print("="*70)
    print(f"\n📋 Config:")
    print(f"   Period: {START_DATE} to {END_DATE}")
    print(f"   Tickers: {', '.join(selected_tickers)}")
    print(f"   TP: {TP_PCT:.1%}, SL: {SL_PCT:.1%}, Max Hold: {MAX_HOLD_DAYS} days")
    print(f"   Capital: ${CAPITAL:.0f}, Max Positions: {MAX_POSITIONS}")
    
    # Filter intraday to selected tickers
    intraday_df = intraday_df[intraday_df['ticker'].isin(selected_tickers)].copy()
    
    # Get unique trading dates
    trading_dates = sorted(intraday_df['datetime'].dt.date.unique())
    
    print(f"\n📊 Data:")
    print(f"   Trading dates: {len(trading_dates)}")
    print(f"   Total intraday bars: {len(intraday_df)}")
    
    # Track portfolio state
    cash = CAPITAL
    positions = {}  # ticker -> Trade dict
    closed_trades = []
    last_entry_date = {}  # ticker -> last entry date to avoid multiple entries same day
    
    # Process bar by bar
    for bar_idx, row in intraday_df.iterrows():
        if bar_idx % 5000 == 0:
            print(f"   Processing bar {bar_idx}/{len(intraday_df)}...")
        
        ticker = row['ticker']
        current_price = row['close']
        current_datetime = row['datetime']
        current_date = current_datetime.date()
        
        # ====================================================================
        # CHECK EXISTING POSITIONS FOR EXIT SIGNALS
        # ====================================================================
        
        closed_this_bar = []
        for pos_ticker in list(positions.keys()):
            trade = positions[pos_ticker]
            
            # Check TP/SL
            hit = False
            if current_price >= trade['tp_price']:
                trade['exit_date'] = current_datetime
                trade['exit_price'] = trade['tp_price']
                trade['exit_reason'] = 'TP'
                hit = True
            elif current_price <= trade['sl_price']:
                trade['exit_date'] = current_datetime
                trade['exit_price'] = trade['sl_price']
                trade['exit_reason'] = 'SL'
                hit = True
            else:
                # Check timeout (max_hold_bars)
                bars_held = bar_idx - trade['entry_bar_idx']
                bars_per_session = 26
                days_held = bars_held / bars_per_session
                if days_held >= MAX_HOLD_DAYS:
                    trade['exit_date'] = current_datetime
                    trade['exit_price'] = current_price * (1 - SLIPPAGE_PCT)
                    trade['exit_reason'] = 'TO'
                    hit = True
            
            if hit:
                # Close trade
                pnl = (trade['exit_price'] - trade['entry_price_with_slip']) - COMMISSION
                pnl_pct = pnl / trade['entry_price_with_slip']
                
                trade['pnl'] = pnl
                trade['pnl_pct'] = pnl_pct
                
                closed_trades.append(trade)
                closed_this_bar.append(pos_ticker)
                
                # Free up capital and position slot
                cash += trade['position_size'] + pnl
        
        # Remove closed positions
        for tk in closed_this_bar:
            del positions[tk]
        
        # ====================================================================
        # ATTEMPT ENTRY IF WE HAVE SLOTS & CASH
        # ====================================================================
        
        # Only attempt entry at market open (first 15m bar of day)
        bars_in_session = 26
        bar_in_session = bar_idx % bars_in_session if bar_idx > 0 else 0
        
        if (len(positions) < MAX_POSITIONS and 
            ticker not in positions and 
            bar_in_session <= 1):  # Only at open
            
            # Check if we already entered this ticker today
            today = current_date
            if ticker in last_entry_date and last_entry_date[ticker] == today:
                continue  # Already entered this ticker today
            
            # Check if forecast has signal for this ticker on this date
            # (Just check existence, don't use prob_win for entry - it's poorly calibrated)
            forecast_mask = (forecast_df['ticker'] == ticker) & (forecast_df['date'].dt.date == current_date)
            forecast_row = forecast_df[forecast_mask]
            
            if len(forecast_row) > 0:
                prob_win = forecast_row['prob_win'].iloc[0]
                
                # Entry filters:
                # 1. MC EV must be positive (or ticker not in MC metrics)
                # 2. prob_win > 0.50 (lowered from 0.55 for more trades)
                mc_ev = mc_metrics[ticker]['ev'] if ticker in mc_metrics else 0
                
                if prob_win > 0.50 and mc_ev >= 0:
                    # MC-weighted position sizing
                    # Base allocation
                    available_slots = MAX_POSITIONS - len(positions)
                    base_position = cash / available_slots
                    
                    # Weight by MC normalized score (0 to 1)
                    # Higher MC score = larger position
                    mc_weight = mc_metrics[ticker]['mc_normalized'] if ticker in mc_metrics else 0.5
                    
                    # Apply weight: 0.5x to 1.5x based on MC score
                    size_multiplier = 0.5 + mc_weight
                    position_size = base_position * size_multiplier
                    
                    # Cap to avoid over-allocation
                    position_size = min(position_size, cash)
                    
                    # Entry prices with slippage
                    entry_price_with_slip = current_price * (1 + SLIPPAGE_PCT)
                    tp_price = entry_price_with_slip * (1 + TP_PCT)
                    sl_price = entry_price_with_slip * (1 - SL_PCT)
                    
                    trade = {
                        'ticker': ticker,
                        'entry_date': current_datetime,
                        'entry_bar_idx': bar_idx,
                        'entry_price': current_price,
                        'entry_price_with_slip': entry_price_with_slip,
                        'tp_price': tp_price,
                        'sl_price': sl_price,
                        'position_size': position_size,
                        'prob_win_forecast': prob_win,
                        'mc_score': mc_metrics[ticker]['mc_score'] if ticker in mc_metrics else 0,
                        'mc_normalized': mc_metrics[ticker]['mc_normalized'] if ticker in mc_metrics else 0.5,
                        'mc_ev': mc_metrics[ticker]['ev'] if ticker in mc_metrics else 0,
                        'exit_date': None,
                        'exit_price': None,
                        'exit_reason': None,
                        'pnl': None,
                        'pnl_pct': None,
                    }
                    
                    positions[ticker] = trade
                    last_entry_date[ticker] = today
                    cash -= position_size
    
    # ====================================================================
    # CLOSE REMAINING POSITIONS AT END
    # ====================================================================
    
    last_close_data = intraday_df.groupby('ticker')['close'].last().to_dict()
    for pos_ticker, trade in positions.items():
        exit_price = last_close_data.get(pos_ticker, trade['entry_price'])
        pnl = (exit_price - trade['entry_price_with_slip']) - COMMISSION
        pnl_pct = pnl / trade['entry_price_with_slip']
        
        trade['exit_date'] = intraday_df['datetime'].max()
        trade['exit_price'] = exit_price
        trade['exit_reason'] = 'END'
        trade['pnl'] = pnl
        trade['pnl_pct'] = pnl_pct
        
        closed_trades.append(trade)
    
    # ====================================================================
    # SUMMARY STATS
    # ====================================================================
    
    total_trades = len(closed_trades)
    if total_trades == 0:
        print("\n❌ No trades executed!")
        return {}
    
    trades_df = pd.DataFrame(closed_trades)
    
    tp_hits = len(trades_df[trades_df['exit_reason'] == 'TP'])
    sl_hits = len(trades_df[trades_df['exit_reason'] == 'SL'])
    timeouts = len(trades_df[trades_df['exit_reason'].isin(['TO', 'END'])])
    
    total_pnl = trades_df['pnl'].sum()
    win_count = len(trades_df[trades_df['pnl'] > 0])
    win_rate = win_count / total_trades if total_trades > 0 else 0
    
    avg_pnl_per_trade = total_pnl / total_trades
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if win_count > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if (total_trades - win_count) > 0 else 0
    
    profit_factor = (trades_df[trades_df['pnl'] > 0]['pnl'].sum() / abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())) if len(trades_df[trades_df['pnl'] < 0]) > 0 else np.inf
    
    summary = {
        'period': f"{START_DATE} to {END_DATE}",
        'selected_tickers': selected_tickers,
        'total_trades': total_trades,
        'wins': win_count,
        'losses': total_trades - win_count,
        'win_rate': float(win_rate),
        'tp_hits': tp_hits,
        'sl_hits': sl_hits,
        'timeouts': timeouts,
        'total_pnl': float(total_pnl),
        'avg_pnl_per_trade': float(avg_pnl_per_trade),
        'avg_win': float(avg_win),
        'avg_loss': float(avg_loss),
        'profit_factor': float(profit_factor),
        'initial_capital': CAPITAL,
        'final_balance': float(CAPITAL + total_pnl),
        'return_pct': float(total_pnl / CAPITAL),
    }
    
    # Print results
    print("\n" + "="*70)
    print("📊 BACKTEST RESULTS (FULL OOS WINDOW)")
    print("="*70)
    print(f"\n💰 P&L:")
    print(f"   Total: ${total_pnl:.2f}")
    print(f"   Return: {summary['return_pct']:+.2%}")
    print(f"   Final Capital: ${summary['final_balance']:.2f}")
    
    print(f"\n📈 Performance:")
    print(f"   Trades: {total_trades}")
    print(f"   Wins: {win_count} | Losses: {total_trades - win_count}")
    print(f"   Win Rate: {win_rate:.1%}")
    print(f"   Avg P&L/Trade: ${avg_pnl_per_trade:.2f}")
    print(f"   Profit Factor: {profit_factor:.2f}x")
    
    print(f"\n🎯 Exit Distribution:")
    print(f"   TP Hits: {tp_hits} ({tp_hits/total_trades:.1%})")
    print(f"   SL Hits: {sl_hits} ({sl_hits/total_trades:.1%})")
    print(f"   Timeouts: {timeouts} ({timeouts/total_trades:.1%})")
    
    # Save results
    output_dir = Path("evidence/backtest_hybrid_gate_full")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save summary
    summary_file = output_dir / "summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Save detailed trades
    trades_file = output_dir / "trades.csv"
    trades_df.to_csv(trades_file, index=False)
    
    print(f"\n✅ Results saved:")
    print(f"   {summary_file}")
    print(f"   {trades_file}")
    
    return summary

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n🚀 HYBRID GATE BACKTEST - FULL OOS")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load data
    print("\n📂 Loading data...")
    intraday_df = load_intraday()
    selected_tickers, mc_metrics = load_gate_selection()
    forecast_df = load_forecast()
    
    print(f"   ✓ Intraday: {len(intraday_df)} bars, {intraday_df['ticker'].nunique()} tickers")
    print(f"   ✓ Selected: {', '.join(selected_tickers)}")
    print(f"   ✓ MC Metrics: {len(mc_metrics)} tickers")
    for tk, metrics in mc_metrics.items():
        print(f"      {tk}: MC={metrics['mc_normalized']:.3f}, EV=${metrics['ev']:.4f}, Hybrid={metrics['hybrid_score']:.3f}")
    print(f"   ✓ Forecast: {len(forecast_df)} signals")
    
    # Run backtest
    summary = run_backtest(selected_tickers, mc_metrics, intraday_df, forecast_df)
