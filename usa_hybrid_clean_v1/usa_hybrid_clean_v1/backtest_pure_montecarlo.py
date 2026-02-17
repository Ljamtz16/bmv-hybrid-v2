#!/usr/bin/env python3
"""
backtest_pure_montecarlo.py
Backtest usando SOLO selección Monte Carlo (sin prob_win forecast)

- Calcula MC scores para TODOS los tickers del universo
- Selecciona top-4 por score MC puro
- Opera durante ventana completa sin filtro de forecast
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# ============================================================================
# CONFIG
# ============================================================================

INTRADAY_FILE = "C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet"

TP_PCT = 0.016  # 1.6%
SL_PCT = 0.010  # 1.0%
MAX_HOLD_DAYS = 2
CAPITAL = 1000.0
MAX_POSITIONS = 4  # Top-4 tickers
COMMISSION = 0.0
SLIPPAGE_PCT = 0.0001

START_DATE = "2024-02-21"
END_DATE = "2025-12-31"

# Monte Carlo config
MC_PATHS = 400
MC_LOOKBACK_DAYS = 20
BLOCK_SIZE = 4
LAMBDA_CVAR = 0.5
MU_LOSS_PROB = 1.0

# Weekly rebalancing
REBALANCE_FREQ_DAYS = 5  # 1 week (5 trading days)

# Trade reduction filters
MIN_MC_EV = 0.3  # Only trade if MC EV > $0.30
MAX_TRADES_PER_DAY = 2  # Max 2 entries per day across all tickers

# ============================================================================
# MONTE CARLO SIMULATION
# ============================================================================

def monte_carlo_simulation(ticker_data: pd.DataFrame, seed: int = 42) -> Dict:
    """Monte Carlo simulation for a ticker."""
    np.random.seed(seed)
    
    if len(ticker_data) < BLOCK_SIZE * 2:
        return None
    
    bars = ticker_data.reset_index(drop=True)
    returns = (bars['close'].pct_change().fillna(0)).values
    
    n_bars = len(returns)
    n_blocks = max(1, n_bars - BLOCK_SIZE + 1)
    blocks = [returns[i:i+BLOCK_SIZE] for i in range(n_blocks)]
    
    tp_pct = TP_PCT
    sl_pct = SL_PCT
    
    pnl_array = []
    tp_count = 0
    sl_count = 0
    to_count = 0
    
    bars_per_session = 26
    max_bars = bars_per_session * MAX_HOLD_DAYS
    
    for path_idx in range(MC_PATHS):
        simulated_returns = np.concatenate([
            blocks[np.random.randint(0, len(blocks))]
            for _ in range(max(1, max_bars // BLOCK_SIZE + 1))
        ])[:max_bars]
        
        last_price = bars['close'].iloc[-1]
        entry_price = last_price
        
        cumsum_returns = np.cumsum(simulated_returns)
        prices = entry_price * (1 + cumsum_returns)
        
        entry_price_with_slip = entry_price * (1 + SLIPPAGE_PCT)
        
        tp_price = entry_price_with_slip * (1 + tp_pct)
        sl_price = entry_price_with_slip * (1 - sl_pct)
        
        hit_bar = None
        for bar_idx, price in enumerate(prices):
            if price >= tp_price:
                hit_bar = bar_idx
                pnl = (tp_price - entry_price_with_slip) - COMMISSION
                tp_count += 1
                break
            elif price <= sl_price:
                hit_bar = bar_idx
                pnl = (sl_price - entry_price_with_slip) - COMMISSION
                sl_count += 1
                break
        
        if hit_bar is None:
            exit_price = prices[-1] * (1 - SLIPPAGE_PCT)
            pnl = (exit_price - entry_price_with_slip) - COMMISSION
            to_count += 1
        
        pnl_array.append(pnl)
    
    pnl_array = np.array(pnl_array)
    
    ev = np.mean(pnl_array)
    prob_loss = np.mean(pnl_array < 0)
    
    var_95_idx = int(len(pnl_array) * 0.05)
    worst_pnls = np.sort(pnl_array)[:var_95_idx] if var_95_idx > 0 else pnl_array[pnl_array < 0]
    cvar_95 = np.mean(worst_pnls) if len(worst_pnls) > 0 else 0
    
    total_trades = MC_PATHS
    tp_rate = tp_count / total_trades if total_trades > 0 else 0
    sl_rate = sl_count / total_trades if total_trades > 0 else 0
    
    score = ev - LAMBDA_CVAR * abs(cvar_95) - MU_LOSS_PROB * prob_loss
    
    return {
        'ev': float(ev),
        'cvar_95': float(cvar_95),
        'prob_loss': float(prob_loss),
        'tp_rate': float(tp_rate),
        'sl_rate': float(sl_rate),
        'score': float(score),
    }

# ============================================================================
# TICKER SELECTION
# ============================================================================

def select_tickers_by_montecarlo(intraday_df: pd.DataFrame, asof_date: str, top_k: int = 4) -> tuple:
    """Select top-K tickers by Monte Carlo score."""
    
    print("\n" + "="*70)
    print("🎲 MONTE CARLO TICKER SELECTION")
    print("="*70)
    
    asof_dt = pd.to_datetime(asof_date)
    start_dt = asof_dt - timedelta(days=MC_LOOKBACK_DAYS * 2)  # Buffer for weekends
    
    # Filter to lookback window
    df_window = intraday_df[
        (intraday_df['datetime'] >= start_dt) & 
        (intraday_df['datetime'] <= asof_dt)
    ].copy()
    
    # Get unique tickers
    all_tickers = sorted(df_window['ticker'].unique())
    
    print(f"\n📊 Universe: {len(all_tickers)} tickers")
    print(f"   Lookback: {MC_LOOKBACK_DAYS} days")
    print(f"   MC Paths: {MC_PATHS}")
    print(f"\n🔬 Running MC simulation...")
    
    mc_results = {}
    
    for ticker in all_tickers:
        ticker_data = df_window[df_window['ticker'] == ticker].sort_values('datetime')
        
        if len(ticker_data) < BLOCK_SIZE * 10:
            continue
        
        result = monte_carlo_simulation(ticker_data, seed=42 + hash(ticker) % 1000)
        
        if result is not None:
            mc_results[ticker] = result
            print(f"   {ticker:6s}: Score={result['score']:7.4f}, EV=${result['ev']:7.4f}, TP={result['tp_rate']:.1%}")
    
    # Rank by MC score
    ranked = sorted(mc_results.items(), key=lambda x: x[1]['score'], reverse=True)
    
    top_tickers = [ticker for ticker, _ in ranked[:top_k]]
    top_metrics = {ticker: metrics for ticker, metrics in ranked[:top_k]}
    
    print(f"\n🏆 TOP-{top_k} SELECTED:")
    for rank, (ticker, metrics) in enumerate(ranked[:top_k], 1):
        print(f"   {rank}. {ticker:6s} | Score: {metrics['score']:7.4f} | EV: ${metrics['ev']:7.4f} | TP: {metrics['tp_rate']:.1%}")
    
    return top_tickers, top_metrics

# ============================================================================
# BACKTEST
# ============================================================================

def run_backtest_weekly_rebalance(intraday_df: pd.DataFrame) -> Dict:
    """Run backtest with WEEKLY ticker reselection via Monte Carlo."""
    
    print("\n" + "="*70)
    print("🎯 PURE MONTE CARLO BACKTEST (WEEKLY REBALANCE)")
    print("="*70)
    print(f"\n📋 Config:")
    print(f"   Period: {START_DATE} to {END_DATE}")
    print(f"   Rebalance: Every {REBALANCE_FREQ_DAYS} days (weekly)")
    print(f"   TP: {TP_PCT:.1%}, SL: {SL_PCT:.1%}, Max Hold: {MAX_HOLD_DAYS} days")
    print(f"   Capital: ${CAPITAL:.0f}, Max Positions: {MAX_POSITIONS}")
    print(f"   Filters: MC EV > ${MIN_MC_EV:.2f}, Max {MAX_TRADES_PER_DAY} trades/day")
    
    # Filter to backtest period
    start_dt = pd.to_datetime(START_DATE)
    end_dt = pd.to_datetime(END_DATE)
    
    backtest_df = intraday_df[
        (intraday_df['datetime'] >= start_dt) &
        (intraday_df['datetime'] <= end_dt)
    ].copy()
    
    all_trading_dates = sorted(backtest_df['datetime'].dt.date.unique())
    
    print(f"\n📊 Data:")
    print(f"   Trading dates: {len(all_trading_dates)}")
    print(f"   Rebalances: {len(all_trading_dates) // REBALANCE_FREQ_DAYS}")
    
    # Track selected tickers per week
    selected_tickers = []
    mc_metrics = {}
    last_rebalance_date = None
    rebalance_count = 0
    
    # Portfolio state
    cash = CAPITAL
    positions = {}
    closed_trades = []
    last_entry_date = {}
    trades_today = 0
    current_trading_date = None
    
    # Process bar by bar
    for bar_idx, row in backtest_df.iterrows():
        if bar_idx % 10000 == 0:
            print(f"   Processing bar {bar_idx}/{len(backtest_df)}...")
        
        ticker = row['ticker']
        current_price = row['close']
        current_datetime = row['datetime']
        current_date = current_datetime.date()
        
        # Reset daily trade counter
        if current_trading_date != current_date:
            current_trading_date = current_date
            trades_today = 0
        
        # Weekly rebalancing: reselect tickers
        if last_rebalance_date is None or (current_date - last_rebalance_date).days >= REBALANCE_FREQ_DAYS:
            # Run MC on data up to current_date
            print(f"\n🔄 Rebalancing on {current_date}...")
            selected_tickers, mc_metrics = select_tickers_by_montecarlo(
                intraday_df[intraday_df['datetime'] < current_datetime],
                str(current_date),
                top_k=MAX_POSITIONS
            )
            last_rebalance_date = current_date
            rebalance_count += 1
            print(f"   Selected: {', '.join(selected_tickers)}")
        
        # Skip if ticker not in current selection
        if ticker not in selected_tickers:
            continue
        
        # Check exits
        closed_this_bar = []
        for pos_ticker in list(positions.keys()):
            trade = positions[pos_ticker]
            
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
                bars_held = bar_idx - trade['entry_bar_idx']
                days_held = bars_held / 26
                if days_held >= MAX_HOLD_DAYS:
                    trade['exit_date'] = current_datetime
                    trade['exit_price'] = current_price * (1 - SLIPPAGE_PCT)
                    trade['exit_reason'] = 'TO'
                    hit = True
            
            if hit:
                pnl = (trade['exit_price'] - trade['entry_price_with_slip']) - COMMISSION
                trade['pnl'] = pnl
                trade['pnl_pct'] = pnl / trade['entry_price_with_slip']
                
                closed_trades.append(trade)
                closed_this_bar.append(pos_ticker)
                cash += trade['position_size'] + pnl
        
        for tk in closed_this_bar:
            del positions[tk]
        
        # Attempt entry (at open only)
        bar_in_session = bar_idx % 26
        
        if (len(positions) < MAX_POSITIONS and 
            ticker not in positions and 
            bar_in_session <= 1 and
            trades_today < MAX_TRADES_PER_DAY):  # Daily trade limit
            
            today = current_date
            if ticker in last_entry_date and last_entry_date[ticker] == today:
                continue
            
            # Filter: Only enter if MC EV is strong enough
            if ticker not in mc_metrics:
                continue
            
            mc_ev = mc_metrics[ticker]['ev']
            if mc_ev < MIN_MC_EV:
                continue  # Skip low-quality setups
            
            # MC-weighted position sizing
            available_slots = MAX_POSITIONS - len(positions)
            base_position = cash / available_slots
            
            # Weight by MC score (normalize to 0.5-1.5x range)
            mc_score_norm = mc_metrics[ticker]['score'] if ticker in mc_metrics else 0
            all_scores = [m['score'] for m in mc_metrics.values()]
            score_min, score_max = min(all_scores), max(all_scores)
            score_range = score_max - score_min if score_max > score_min else 1
            mc_weight = (mc_score_norm - score_min) / score_range  # 0 to 1
            
            size_multiplier = 0.5 + mc_weight
            position_size = min(base_position * size_multiplier, cash)
            
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
                'mc_score': mc_metrics[ticker]['score'],
                'mc_ev': mc_metrics[ticker]['ev'],
                'mc_tp_rate': mc_metrics[ticker]['tp_rate'],
                'exit_date': None,
                'exit_price': None,
                'exit_reason': None,
                'pnl': None,
                'pnl_pct': None,
            }
            
            positions[ticker] = trade
            last_entry_date[ticker] = today
            cash -= position_size
            trades_today += 1
    
    # Close remaining
    last_close_data = backtest_df.groupby('ticker')['close'].last().to_dict()
    for pos_ticker, trade in positions.items():
        exit_price = last_close_data.get(pos_ticker, trade['entry_price'])
        pnl = (exit_price - trade['entry_price_with_slip']) - COMMISSION
        
        trade['exit_date'] = backtest_df['datetime'].max()
        trade['exit_price'] = exit_price
        trade['exit_reason'] = 'END'
        trade['pnl'] = pnl
        trade['pnl_pct'] = pnl / trade['entry_price_with_slip']
        
        closed_trades.append(trade)
    
    print(f"\n📊 Rebalance Summary: {rebalance_count} rebalances over {len(all_trading_dates)} days")
    
    # Summary
    total_trades = len(closed_trades)
    if total_trades == 0:
        print("\n❌ No trades!")
        return {}
    
    trades_df = pd.DataFrame(closed_trades)
    
    tp_hits = len(trades_df[trades_df['exit_reason'] == 'TP'])
    sl_hits = len(trades_df[trades_df['exit_reason'] == 'SL'])
    timeouts = len(trades_df[trades_df['exit_reason'].isin(['TO', 'END'])])
    
    total_pnl = trades_df['pnl'].sum()
    win_count = len(trades_df[trades_df['pnl'] > 0])
    win_rate = win_count / total_trades
    
    avg_pnl = total_pnl / total_trades
    profit_factor = (trades_df[trades_df['pnl'] > 0]['pnl'].sum() / 
                    abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())) if len(trades_df[trades_df['pnl'] < 0]) > 0 else np.inf
    
    # Get all unique tickers traded
    all_tickers_traded = sorted(trades_df['ticker'].unique().tolist())
    
    summary = {
        'period': f"{START_DATE} to {END_DATE}",
        'rebalances': rebalance_count,
        'all_tickers_traded': all_tickers_traded,
        'total_trades': total_trades,
        'wins': win_count,
        'win_rate': float(win_rate),
        'tp_hits': tp_hits,
        'sl_hits': sl_hits,
        'timeouts': timeouts,
        'total_pnl': float(total_pnl),
        'avg_pnl_per_trade': float(avg_pnl),
        'profit_factor': float(profit_factor),
        'final_balance': float(CAPITAL + total_pnl),
        'return_pct': float(total_pnl / CAPITAL),
    }
    
    print("\n" + "="*70)
    print("📊 BACKTEST RESULTS")
    print("="*70)
    print(f"\n💰 P&L:")
    print(f"   Total: ${total_pnl:.2f}")
    print(f"   Return: {summary['return_pct']:+.2%}")
    print(f"   Final: ${summary['final_balance']:.2f}")
    
    print(f"\n📈 Performance:")
    print(f"   Trades: {total_trades}")
    print(f"   Win Rate: {win_rate:.1%} ({win_count}W / {total_trades-win_count}L)")
    print(f"   Avg P&L: ${avg_pnl:.2f}")
    print(f"   Profit Factor: {profit_factor:.2f}x")
    
    print(f"\n🎯 Exits:")
    print(f"   TP: {tp_hits} ({tp_hits/total_trades:.1%})")
    print(f"   SL: {sl_hits} ({sl_hits/total_trades:.1%})")
    print(f"   TO: {timeouts} ({timeouts/total_trades:.1%})")
    
    # Per-ticker breakdown
    print(f"\n📊 Per-Ticker (All {len(all_tickers_traded)} traded):")
    for ticker in all_tickers_traded:
        ticker_trades = trades_df[trades_df['ticker'] == ticker]
        ticker_pnl = ticker_trades['pnl'].sum()
        ticker_wins = len(ticker_trades[ticker_trades['pnl'] > 0])
        ticker_wr = ticker_wins / len(ticker_trades)
        print(f"   {ticker:6s}: {len(ticker_trades):3d} trades | WR {ticker_wr:.1%} | P&L ${ticker_pnl:+7.2f}")
    
    # Save
    output_dir = Path("evidence/backtest_mc_weekly_2024_2025")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    trades_df.to_csv(output_dir / "trades.csv", index=False)
    
    print(f"\n✅ Saved: {output_dir}")
    
    return summary

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n🚀 PURE MONTE CARLO BACKTEST")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load intraday
    print("\n📂 Loading intraday data...")
    df = pd.read_parquet(INTRADAY_FILE)
    
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], utc=False)
    else:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    
    if df['datetime'].dt.tz is not None:
        df['datetime'] = df['datetime'].dt.tz_localize(None)
    
    print(f"   ✓ Loaded: {len(df)} bars, {df['ticker'].nunique()} tickers")
    
    # Run backtest with weekly rebalancing
    summary = run_backtest_weekly_rebalance(df)
