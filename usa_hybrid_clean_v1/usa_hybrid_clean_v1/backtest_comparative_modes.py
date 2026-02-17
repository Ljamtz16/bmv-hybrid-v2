"""
Comparative Backtest: Baseline vs Hybrid vs ProbWin-Only

Modes:
  A) baseline: Pure MC (no prob_win filtering)
  B) hybrid: MC + prob_win_retrained gating/sizing
  C) probwin_only: Only prob_win_retrained for signal generation

Usage:
  python backtest_comparative_modes.py --mode baseline
  python backtest_comparative_modes.py --mode hybrid --pw_threshold 0.55
  python backtest_comparative_modes.py --mode hybrid --pw_bands 0.52,0.58
  python backtest_comparative_modes.py --mode probwin_only --pw_threshold 0.55
"""

import pandas as pd
import numpy as np
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

# ==============================================================================
# CONFIG
# ==============================================================================
INTRADAY_FILE = r"C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\data\us\intraday_15m\consolidated_15m.parquet"
FORECAST_FILE = "evidence/forecast_retrained_robust/forecast_prob_win_retrained.parquet"

# Strategy parameters
TP_PCT = 1.6 / 100
SL_PCT = 1.0 / 100
MAX_HOLD_DAYS = 2
CAPITAL = 2000
MAX_POSITIONS = 4
MAX_DEPLOY = 1900  # Never deploy more than this
PER_TRADE_CASH = 500  # max_deploy / max_positions = 1900 / 4 = 475, set to 500
SLIPPAGE_PCT = 0.01 / 100

# Period
START_DATE = "2024-01-01"
END_DATE = "2025-12-31"

# MC parameters
MC_PATHS = 400
MC_LOOKBACK = 20
MC_BLOCK_SIZE = 4

# Rebalance for dynamic selection
REBALANCE_FREQ_DAYS = 5
MIN_MC_EV = 0.003
MAX_TRADES_PER_DAY = 2

# Universe restriction (None = all tickers, or list like ['AAPL', 'GS', ...])
TICKER_UNIVERSE = None

# ==============================================================================
# TRADE SCHEMA + PNL COLUMN RESOLUTION
# ==============================================================================
EXPECTED_TRADE_COLS = [
    'ticker', 'entry_date', 'entry_price', 'exit_date', 'exit_price', 'exit_reason',
    'pnl', 'pnl_pct', 'size', 'prob_win', 'mc_score', 'mc_ev'
]

def ensure_trade_schema(df):
    """Ensure trades dataframe has expected columns even when empty."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=EXPECTED_TRADE_COLS)
    # add any missing columns
    for c in EXPECTED_TRADE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    return df

def resolve_pnl_col(df):
    """Resolve the actual PnL column name present in df."""
    candidates = ['pnl', 'net_pnl', 'pnl_usd', 'profit', 'return', 'pnl_mxn']
    for c in candidates:
        if c in df.columns:
            return c
    return None

# ==============================================================================
# MONTE CARLO SIMULATION
# ==============================================================================
def monte_carlo_simulation(returns, tp_pct=TP_PCT, sl_pct=SL_PCT, max_hold=MAX_HOLD_DAYS, n_paths=MC_PATHS, block_size=MC_BLOCK_SIZE):
    """Run block bootstrap Monte Carlo"""
    if len(returns) < 10:
        return {'ev': 0, 'cvar': 0, 'prob_loss': 1.0, 'score': -999, 'tp_rate': 0, 'sl_rate': 0}
    
    returns = np.array(returns)
    n = len(returns)
    pnls = []
    tp_count = 0
    sl_count = 0
    
    for _ in range(n_paths):
        # Block bootstrap
        cumret = 0
        for day in range(max_hold):
            if day >= n:
                break
            block_start = np.random.randint(0, max(1, n - block_size + 1))
            block = returns[block_start:block_start + block_size]
            ret = np.random.choice(block)
            cumret += ret
            
            # TP/SL check
            if cumret >= tp_pct:
                pnls.append(tp_pct)
                tp_count += 1
                break
            elif cumret <= -sl_pct:
                pnls.append(-sl_pct)
                sl_count += 1
                break
        else:
            pnls.append(cumret)
    
    pnls = np.array(pnls)
    ev = np.mean(pnls)
    cvar = -np.percentile(pnls, 5)
    prob_loss = (pnls < 0).mean()
    score = ev - cvar
    
    return {
        'ev': ev,
        'cvar': cvar,
        'prob_loss': prob_loss,
        'score': score,
        'tp_rate': tp_count / n_paths,
        'sl_rate': sl_count / n_paths
    }

def select_tickers_by_mc(daily_df, current_date, lookback_days=MC_LOOKBACK, top_k=MAX_POSITIONS):
    """Select top-K tickers by MC score"""
    end_date = current_date
    start_date = current_date - timedelta(days=lookback_days)
    
    window_data = daily_df[
        (daily_df['date'] >= start_date) & 
        (daily_df['date'] < end_date)
    ]
    
    scores = {}
    for ticker in daily_df['ticker'].unique():
        ticker_data = window_data[window_data['ticker'] == ticker]
        if len(ticker_data) < 10:
            continue
        
        returns = ticker_data['return'].dropna().values
        mc_result = monte_carlo_simulation(returns)
        scores[ticker] = mc_result
    
    # Rank by score
    ranked = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    return [t[0] for t in ranked[:top_k]], {t[0]: t[1] for t in ranked}

# ==============================================================================
# LOAD DATA
# ==============================================================================
def load_data(mode, forecast_path=None, ticker_universe=None):
    """Load intraday data and optional forecast"""
    print("=" * 80)
    print(f"Loading data for mode: {mode}")
    if ticker_universe:
        print(f"Universe restricted to: {ticker_universe}")
    print("=" * 80)
    
    # Load intraday (full), then filter for trading range; keep warmup for MC lookback
    intraday_all = pd.read_parquet(INTRADAY_FILE)
    intraday_all['date'] = pd.to_datetime(intraday_all['timestamp']).dt.tz_localize(None)
    
    start_dt = pd.to_datetime(START_DATE)
    end_dt = pd.to_datetime(END_DATE)
    warmup_start = start_dt - timedelta(days=MC_LOOKBACK + 5)
    
    # Intraday for trading (iteration)
    intraday_df = intraday_all[(intraday_all['date'] >= start_dt) & (intraday_all['date'] <= end_dt)].copy()
    
    # Aggregate to daily for MC using warmup window
    intraday_for_daily = intraday_all[(intraday_all['date'] >= warmup_start) & (intraday_all['date'] <= end_dt)].copy()
    
    # Normalize ticker_universe
    ticker_universe = [t.strip().upper() for t in (ticker_universe or []) if str(t).strip()]
    
    # Apply ticker universe restriction if specified
    if ticker_universe:
        intraday_df = intraday_df[intraday_df['ticker'].isin(ticker_universe)].copy()
        intraday_for_daily = intraday_for_daily[intraday_for_daily['ticker'].isin(ticker_universe)].copy()
    
    print(f"[OK] Loaded {len(intraday_df)} intraday bars")
    
    daily_df = intraday_for_daily.groupby(['ticker', intraday_for_daily['date'].dt.date]).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).reset_index()
    daily_df['date'] = pd.to_datetime(daily_df['date'])
    daily_df = daily_df.sort_values(['ticker', 'date'])
    
    # Compute returns
    daily_df['return'] = daily_df.groupby('ticker')['close'].pct_change()
    
    print(f"[OK] Aggregated to {len(daily_df)} daily bars")
    
    # Load forecast if needed
    forecast_df = None
    if mode in ['hybrid', 'probwin_only', 'hybrid_full_universe'] and forecast_path:
        forecast_df = pd.read_parquet(forecast_path)
        forecast_df['date'] = pd.to_datetime(forecast_df['date'])
        
        # Rename column to standard name if needed
        if 'prob_win_retrained' in forecast_df.columns:
            forecast_df['prob_win'] = forecast_df['prob_win_retrained']
        
        forecast_df = forecast_df[['ticker', 'date', 'prob_win']]
        print(f"[OK] Loaded forecast: {len(forecast_df)} rows")
        print(f"  Mean prob_win: {forecast_df['prob_win'].mean():.1%}")
    
    return intraday_df, daily_df, forecast_df

# ==============================================================================
# BACKTEST ENGINE
# ==============================================================================
def run_backtest(mode, intraday_df, daily_df, forecast_df=None, pw_threshold=None, pw_bands=None, soft_hybrid=False):
    """
    Unified backtest engine
    
    Args:
        mode: 'baseline', 'hybrid', or 'probwin_only'
        pw_threshold: single threshold (e.g. 0.55)
        pw_bands: tuple (low, high) for sizing bands (e.g. (0.52, 0.58))
        soft_hybrid: if True, hybrid uses sizing without blocking trades (≥0.58: 1.0x, 0.52-0.58: 0.8x, <0.52: 0.6x)
    """
    print("\n" + "=" * 80)
    print(f"Running backtest: {mode.upper()}")
    print("=" * 80)
    
    # Setup
    intraday_df = intraday_df.sort_values(['ticker', 'date'])
    trades = []
    equity_curve = []
    cash = CAPITAL
    positions = {}
    deployed_cash = 0  # Track deployed capital for guardrail
    
    # Restrict MC selection universe to forecast-covered tickers for hybrid/probwin_only
    if mode in ['hybrid', 'probwin_only'] and forecast_df is not None:
        allowed = set(forecast_df['ticker'].unique())
        daily_df_sel = daily_df[daily_df['ticker'].isin(allowed)].copy()
    elif mode == 'hybrid_full_universe':
        # For full_universe mode, MC selects from ALL available tickers
        # but ProbWin will veto any without forecast
        daily_df_sel = daily_df.copy()
    else:
        daily_df_sel = daily_df

    # DIAGNOSTIC: Print forecast and daily info
    print("\n" + "=" * 80)
    print("DIAGNOSTIC: Forecast vs Daily Data")
    print("=" * 80)
    print(f"FORECAST tickers: {sorted(forecast_df['ticker'].unique()) if forecast_df is not None else 'N/A'}")
    forecast_lookup = None
    if forecast_df is not None:
        # Precompute fast lookup for prob_win by (ticker, date)
        forecast_df = forecast_df.copy()
        forecast_df['date_only'] = forecast_df['date'].dt.date
        forecast_lookup = dict(zip(zip(forecast_df['ticker'], forecast_df['date_only']), forecast_df['prob_win']))
        print(f"FORECAST date sample: {forecast_df['date'].head(3).tolist()}")
        print(f"FORECAST date dtype: {forecast_df['date'].dtype}")
    print(f"\nDAILY tickers: {sorted(daily_df_sel['ticker'].unique())}")
    print(f"DAILY date sample: {daily_df_sel['date'].head(3).tolist()}")
    print(f"DAILY date dtype: {daily_df_sel['date'].dtype}")
    print("=" * 80 + "\n")

    selected_tickers = []
    mc_scores = {}  # Initialize mc_scores
    last_rebalance_date = None
    trades_today = 0
    current_date = None
    
    # Counter for prob_win availability
    present_pw = 0
    missing_pw = 0
    
    total_bars = len(intraday_df)
    
    for idx, row in intraday_df.iterrows():
        bar_date = row['date']
        bar_date_only = bar_date.date()
        ticker = row['ticker']
        
        # Date change
        if current_date != bar_date_only:
            current_date = bar_date_only
            trades_today = 0
            
            # Rebalance check (for baseline/hybrid with dynamic MC)
            if mode in ['baseline', 'hybrid', 'hybrid_full_universe']:
                if last_rebalance_date is None or (bar_date - last_rebalance_date).days >= REBALANCE_FREQ_DAYS:
                    selected_tickers, mc_scores = select_tickers_by_mc(daily_df_sel, bar_date, MC_LOOKBACK, MAX_POSITIONS)
                    last_rebalance_date = bar_date
                    if idx % 10000 == 0:
                        print(f"  Rebalancing on {bar_date.date()}: {selected_tickers}")
        
        # Check open positions (exits)
        if ticker in positions:
            pos = positions[ticker]
            entry_price = pos['entry_price']
            hold_days = (bar_date - pos['entry_date']).days
            
            tp_price = entry_price * (1 + TP_PCT)
            sl_price = entry_price * (1 - SL_PCT)
            
            exit_reason = None
            exit_price = None
            
            if row['high'] >= tp_price:
                exit_reason = 'TP'
                exit_price = tp_price
            elif row['low'] <= sl_price:
                exit_reason = 'SL'
                exit_price = sl_price
            elif hold_days >= MAX_HOLD_DAYS:
                exit_reason = 'TO'
                exit_price = row['close']
            
            if exit_reason:
                # Close position
                pnl = (exit_price - entry_price) * pos['size'] - (entry_price * pos['size'] * SLIPPAGE_PCT)
                cash += (exit_price * pos['size'])
                deployed_cash -= (entry_price * pos['size'])  # Reduce deployed on exit
                
                trades.append({
                    'ticker': ticker,
                    'entry_date': pos['entry_date'],
                    'entry_price': entry_price,
                    'exit_date': bar_date,
                    'exit_price': exit_price,
                    'exit_reason': exit_reason,
                    'pnl': pnl,
                    'pnl_pct': (exit_price - entry_price) / entry_price,
                    'size': pos['size'],
                    'prob_win': pos.get('prob_win', np.nan),
                    'mc_score': pos.get('mc_score', np.nan),
                    'mc_ev': pos.get('mc_ev', np.nan)
                })
                
                del positions[ticker]
        
        # Entry logic
        if ticker not in positions and len(positions) < MAX_POSITIONS and trades_today < MAX_TRADES_PER_DAY:
            # Mode-specific signal generation
            take_trade = False
            prob_win = None
            mc_score = None
            mc_ev = None
            sizing_mult = 1.0
            
            if mode == 'baseline':
                # Pure MC: only check if ticker selected
                if ticker in selected_tickers:
                    # Check MC EV filter
                    if ticker in mc_scores and mc_scores[ticker]['ev'] >= MIN_MC_EV:
                        take_trade = True
                        mc_score = mc_scores[ticker]['score']
                        mc_ev = mc_scores[ticker]['ev']
            
            elif mode == 'hybrid':
                # MC + prob_win gating
                if ticker in selected_tickers:
                    if ticker in mc_scores and mc_scores[ticker]['ev'] >= MIN_MC_EV:
                        mc_score = mc_scores[ticker]['score']
                        mc_ev = mc_scores[ticker]['ev']
                        
                        # Get prob_win from forecast
                        if forecast_lookup is not None:
                            prob_win = forecast_lookup.get((ticker, bar_date_only))
                            if prob_win is not None:
                                present_pw += 1
                                
                                # Apply gating
                                if soft_hybrid:
                                    # Soft hybrid: always trade, vary sizing
                                    take_trade = True
                                    if prob_win >= 0.58:
                                        sizing_mult = 1.0
                                    elif prob_win >= 0.52:
                                        sizing_mult = 0.8
                                    else:
                                        sizing_mult = 0.6
                                elif pw_threshold is not None:
                                    # Single threshold
                                    if prob_win >= pw_threshold:
                                        take_trade = True
                                elif pw_bands is not None:
                                    # Bands for sizing
                                    low, high = pw_bands
                                    if prob_win >= high:
                                        take_trade = True
                                        sizing_mult = 1.0
                                    elif prob_win >= low:
                                        take_trade = True
                                        sizing_mult = 0.5
                                else:
                                    # No filter
                                    take_trade = True
                            else:
                                missing_pw += 1
            
            elif mode == 'probwin_only':
                # Only prob_win signal
                if forecast_lookup is not None:
                    prob_win = forecast_lookup.get((ticker, bar_date_only))
                    if prob_win is not None:
                        
                        if pw_threshold is not None:
                            if prob_win >= pw_threshold:
                                take_trade = True
                        else:
                            if prob_win >= 0.5:
                                take_trade = True
            
            elif mode == 'hybrid_full_universe':
                # MC proposes from FULL universe, ProbWin decides
                # Always try MC scoring first
                if ticker in mc_scores and mc_scores[ticker]['ev'] >= MIN_MC_EV:
                    mc_score = mc_scores[ticker]['score']
                    mc_ev = mc_scores[ticker]['ev']
                    
                    # Get prob_win from forecast
                    if forecast_lookup is not None:
                        prob_win = forecast_lookup.get((ticker, bar_date_only))
                        if prob_win is not None:
                            present_pw += 1
                            
                            # Hard ProbWin gate
                            if pw_threshold is not None:
                                if prob_win >= pw_threshold:
                                    take_trade = True
                            else:
                                if prob_win >= 0.55:
                                    take_trade = True
                        else:
                            # No forecast = no trade
                            missing_pw += 1
                    else:
                        # No forecast available
                        missing_pw += 1
            
            # Execute trade if signal
            if take_trade:
                entry_price = row['open']
                entry_price_with_slip = entry_price * (1 + SLIPPAGE_PCT)
                position_value = PER_TRADE_CASH * sizing_mult
                size = position_value / entry_price_with_slip
                trade_cash = entry_price_with_slip * size
                
                # Guardrails: max_deploy check + max_open check
                if (deployed_cash + trade_cash <= MAX_DEPLOY and 
                    cash >= trade_cash and
                    len(positions) < MAX_POSITIONS):
                    
                    cash -= trade_cash
                    deployed_cash += trade_cash
                    
                    positions[ticker] = {
                        'entry_date': bar_date,
                        'entry_price': entry_price_with_slip,
                        'size': size,
                        'prob_win': prob_win,
                        'mc_score': mc_score,
                        'mc_ev': mc_ev
                    }
                    
                    trades_today += 1
        
        # Track equity
        if idx % 1000 == 0:
            equity = cash + sum(row['close'] * pos['size'] for t, pos in positions.items() if t == ticker)
            equity_curve.append({'date': bar_date, 'equity': equity})
    
    # Close remaining positions
    for ticker, pos in positions.items():
        last_price = intraday_df[intraday_df['ticker'] == ticker].iloc[-1]['close']
        pnl = (last_price - pos['entry_price']) * pos['size']
        deployed_cash -= (pos['entry_price'] * pos['size'])  # Reduce deployed on close
        cash += (last_price * pos['size'])
        
        trades.append({
            'ticker': ticker,
            'entry_date': pos['entry_date'],
            'entry_price': pos['entry_price'],
            'exit_date': intraday_df['date'].max(),
            'exit_price': last_price,
            'exit_reason': 'FINAL',
            'pnl': pnl,
            'pnl_pct': (last_price - pos['entry_price']) / pos['entry_price'],
            'size': pos['size'],
            'prob_win': pos.get('prob_win', np.nan),
            'mc_score': pos.get('mc_score', np.nan),
            'mc_ev': pos.get('mc_ev', np.nan)
        })
    
    final_equity = cash
    trades_df = pd.DataFrame(trades)
    
    # DIAGNOSTIC: Print prob_win availability
    if mode == 'hybrid':
        print(f"\nDEBUG prob_win present: {present_pw}, missing: {missing_pw}")
    
    return trades_df, final_equity, equity_curve

# ==============================================================================
# ANALYSIS
# ==============================================================================
def analyze_results(trades_df, final_equity, mode):
    """Compute metrics"""
    print("\n" + "=" * 80)
    print(f"RESULTS: {mode.upper()}")
    print("=" * 80)
    
    # Resolve PnL column robustly
    pnl_col = resolve_pnl_col(trades_df)
    
    if pnl_col is None:
        total_pnl = 0.0
        n_trades = int(len(trades_df))
        wins = 0
        losses = 0
        win_rate = 0.0
        profit_factor = 0.0
        avg_pnl = 0.0
    else:
        total_pnl = float(trades_df[pnl_col].fillna(0).sum())
        n_trades = int(len(trades_df))
        wins = int((trades_df[pnl_col] > 0).sum())
        losses = int((trades_df[pnl_col] <= 0).sum())
        win_rate = wins / n_trades if n_trades > 0 else 0.0
        gains = trades_df.loc[trades_df[pnl_col] > 0, pnl_col].sum()
        losses_sum = -trades_df.loc[trades_df[pnl_col] < 0, pnl_col].sum()
        profit_factor = float(gains / losses_sum) if losses_sum > 0 else (float('inf') if gains > 0 else 0.0)
        avg_pnl = float(total_pnl / n_trades) if n_trades > 0 else 0.0

    total_return = (final_equity - CAPITAL) / CAPITAL

    print(f"\nP&L:")
    print(f"   Total: ${total_pnl:.2f}")
    print(f"   Return: {total_return:.1%}")
    print(f"   Final: ${final_equity:.2f}")
    
    print(f"\nPerformance:")
    print(f"   Trades: {n_trades}")
    print(f"   Win Rate: {win_rate:.1%} ({wins}W / {losses}L)")
    print(f"   Avg P&L: ${avg_pnl:.2f}" if n_trades > 0 else "   Avg P&L: N/A")
    print(f"   Profit Factor: {profit_factor if profit_factor != float('inf') else 9999.0:.2f}x")
    
    print(f"\nExits:")
    tp_count = (trades_df['exit_reason'] == 'TP').sum()
    sl_count = (trades_df['exit_reason'] == 'SL').sum()
    to_count = (trades_df['exit_reason'] == 'TO').sum()
    print(f"   TP: {tp_count} ({tp_count/n_trades:.1%})" if n_trades > 0 else "   TP: 0")
    print(f"   SL: {sl_count} ({sl_count/n_trades:.1%})" if n_trades > 0 else "   SL: 0")
    print(f"   TO: {to_count} ({to_count/n_trades:.1%})" if n_trades > 0 else "   TO: 0")
    
    # Per-ticker
    print(f"\nPer-Ticker:")
    for ticker in sorted(trades_df['ticker'].unique()):
        ticker_trades = trades_df[trades_df['ticker'] == ticker]
        ticker_wr = (ticker_trades['pnl'] > 0).mean()
        ticker_pnl = ticker_trades['pnl'].sum()
        print(f"   {ticker:6s}: {len(ticker_trades):3d} trades | WR {ticker_wr:.1%} | P&L ${ticker_pnl:+.2f}")
    
    # Prob_win calibration if available
    if 'prob_win' in trades_df.columns and not trades_df['prob_win'].isna().all():
        print(f"\nProb_Win Calibration:")
        trades_df['pw_decile'] = pd.qcut(trades_df['prob_win'], q=10, labels=False, duplicates='drop')
        calibration = trades_df.groupby('pw_decile').agg({
            'pnl': ['count', lambda x: (x > 0).mean(), 'mean'],
            'prob_win': 'mean'
        })
        print(calibration)
    
    return {
        'mode': mode,
        'total_pnl': float(total_pnl),
        'return_pct': float(total_return * 100),
        'final_equity': float(final_equity),
        'n_trades': int(n_trades),
        'win_rate': float(win_rate),
        'profit_factor': float(profit_factor if profit_factor != float('inf') else 9999.0),
        'avg_pnl_per_trade': float(avg_pnl)
    }

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description='Comparative Backtest')
    parser.add_argument('--mode', required=True, choices=['baseline', 'hybrid', 'probwin_only', 'hybrid_full_universe'])
    parser.add_argument('--forecast', default=FORECAST_FILE, help='Path to forecast file')
    parser.add_argument('--pw_threshold', type=float, help='Prob_win threshold (e.g. 0.55)')
    parser.add_argument('--pw_bands', type=str, help='Prob_win bands (e.g. 0.52,0.58)')
    parser.add_argument('--ticker_universe', type=str, help='Comma-separated list of tickers to restrict universe')
    parser.add_argument('--soft_hybrid', action='store_true', help='Use soft hybrid sizing (no blocking)')
    parser.add_argument('--start_date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default=None, help='Output directory')
    
    args = parser.parse_args()
    
    # Override dates if provided
    global START_DATE, END_DATE
    if args.start_date:
        START_DATE = args.start_date
    if args.end_date:
        END_DATE = args.end_date
    
    # Parse bands
    pw_bands = None
    if args.pw_bands:
        low, high = map(float, args.pw_bands.split(','))
        pw_bands = (low, high)
    
    # Parse ticker universe
    ticker_universe = None
    if args.ticker_universe:
        ticker_universe = [t.strip() for t in args.ticker_universe.split(',')]
    
    # Load data
    intraday_df, daily_df, forecast_df = load_data(args.mode, args.forecast, ticker_universe)
    
    # Run backtest
    trades_df, final_equity, equity_curve = run_backtest(
        args.mode, intraday_df, daily_df, forecast_df,
        pw_threshold=args.pw_threshold,
        pw_bands=pw_bands,
        soft_hybrid=args.soft_hybrid
    )
    
    # Debug quick view
    print("\nDEBUG trades_df shape:", trades_df.shape)
    print("DEBUG trades_df cols:", list(trades_df.columns)[:50])
    print("DEBUG head:\n", trades_df.head(3).to_string(index=False))
    
    # Ensure schema to avoid KeyError on empty DF
    trades_df = ensure_trade_schema(trades_df)
    
    # Analyze
    metrics = analyze_results(trades_df, final_equity, args.mode)
    
    # Save
    output_dir = Path(args.output) if args.output else Path(f"evidence/backtest_{args.mode}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    trades_df.to_csv(output_dir / "trades.csv", index=False)
    
    with open(output_dir / "metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"\n[SUCCESS] Saved to {output_dir}")

if __name__ == '__main__':
    main()
