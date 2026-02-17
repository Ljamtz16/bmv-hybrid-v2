#!/usr/bin/env python3
"""
montecarlo_gate_dynamic.py
Dynamic Monte Carlo Ticker Gate with intra-month rebalancing.

Fase 2: Recalcula Monte Carlo cada semana y permite rotación de tickers.

Usage:
    python montecarlo_gate_dynamic_v2.py --month 2025-03 --rebalance-freq weekly --output-dir evidence/dynamic_gate_mar2025
"""

import argparse
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configuración por defecto
DEFAULT_CONFIG = {
    "n_days": 20,
    "max_hold_days": 2,
    "mc_paths": 400,
    "block_size": 4,
    "top_k": 4,
    "commission": 0.0,
    "slippage_pct": 0.0001,
    "lambda_cvar": 0.5,
    "mu_loss_prob": 1.0,
    "seed": 42,
}

TICKERS_UNIVERSE = ["NVDA", "AMD", "XOM", "CVX", "META", "TSLA", "PFE", "JNJ", "MSFT", "AAPL"]

def load_intraday_data(parquet_path: str, asof_date: str) -> pd.DataFrame:
    """Carga datos intraday 15m hasta asof_date."""
    df = pd.read_parquet(parquet_path)
    
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], utc=False)
    elif df.columns[0] in ['timestamp', 'datetime']:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    else:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    
    if df['datetime'].dt.tz is not None:
        df['datetime'] = df['datetime'].dt.tz_localize(None)
    
    asof_dt = pd.to_datetime(asof_date)
    df = df[df['datetime'] <= asof_dt]
    
    return df

def get_last_n_trading_days(df: pd.DataFrame, n: int) -> List:
    """Retorna los últimos N días hábiles únicos."""
    dates = sorted(df['datetime'].dt.date.unique())
    return dates[-n:] if len(dates) >= n else dates

def monte_carlo_simulation(
    ticker_data: pd.DataFrame,
    max_hold_days: int,
    mc_paths: int,
    block_size: int,
    commission: float,
    slippage_pct: float,
    seed: int = 42
) -> Dict:
    """Simula múltiples caminos de precio para un ticker."""
    np.random.seed(seed)
    
    if len(ticker_data) < block_size * 2:
        return None
    
    bars = ticker_data.reset_index(drop=True)
    returns = (bars['close'].pct_change().fillna(0)).values
    
    n_bars = len(returns)
    n_blocks = max(1, n_bars - block_size + 1)
    blocks = [returns[i:i+block_size] for i in range(n_blocks)]
    
    tp_pct = 0.020
    sl_pct = 0.012
    
    pnl_array = []
    tp_count = 0
    sl_count = 0
    to_count = 0
    hold_bars_list = []
    
    bars_per_session = 26
    max_bars = bars_per_session * max_hold_days
    
    for path_idx in range(mc_paths):
        if len(returns) > bars_per_session:
            path_idx_start = np.random.randint(0, len(returns) - bars_per_session)
        else:
            path_idx_start = 0
            
        simulated_returns = np.concatenate([
            blocks[np.random.randint(0, len(blocks))]
            for _ in range(max(1, max_bars // block_size + 1))
        ])[:max_bars]
        
        last_price = bars['close'].iloc[-1]
        entry_price = last_price
        
        cumsum_returns = np.cumsum(simulated_returns)
        prices = entry_price * (1 + cumsum_returns)
        
        entry_price_with_slip = entry_price * (1 + slippage_pct)
        
        tp_price = entry_price_with_slip * (1 + tp_pct)
        sl_price = entry_price_with_slip * (1 - sl_pct)
        
        hit_bar = None
        for bar_idx, price in enumerate(prices):
            if price >= tp_price:
                hit_bar = bar_idx
                pnl = (tp_price - entry_price_with_slip) - commission
                tp_count += 1
                break
            elif price <= sl_price:
                hit_bar = bar_idx
                pnl = (sl_price - entry_price_with_slip) - commission
                sl_count += 1
                break
        
        if hit_bar is None:
            exit_price = prices[-1] * (1 - slippage_pct)
            pnl = (exit_price - entry_price_with_slip) - commission
            to_count += 1
            hit_bar = len(prices) - 1
        
        pnl_array.append(pnl)
        hold_bars_list.append(hit_bar)
    
    pnl_array = np.array(pnl_array)
    
    ev = np.mean(pnl_array)
    prob_loss = np.mean(pnl_array < 0)
    
    var_95_idx = int(len(pnl_array) * 0.05)
    worst_pnls = np.sort(pnl_array)[:var_95_idx] if var_95_idx > 0 else pnl_array[pnl_array < 0]
    cvar_95 = np.mean(worst_pnls) if len(worst_pnls) > 0 else 0
    
    total_trades = mc_paths
    tp_rate = tp_count / total_trades if total_trades > 0 else 0
    sl_rate = sl_count / total_trades if total_trades > 0 else 0
    to_rate = to_count / total_trades if total_trades > 0 else 0
    
    avg_hold_bars = np.mean(hold_bars_list)
    
    lambda_cvar = DEFAULT_CONFIG["lambda_cvar"]
    mu_loss_prob = DEFAULT_CONFIG["mu_loss_prob"]
    score = ev - lambda_cvar * abs(cvar_95) - mu_loss_prob * prob_loss
    
    return {
        'ev': float(ev),
        'cvar_95': float(cvar_95),
        'prob_loss': float(prob_loss),
        'tp_rate': float(tp_rate),
        'sl_rate': float(sl_rate),
        'to_rate': float(to_rate),
        'avg_hold_bars': float(avg_hold_bars),
        'score': float(score),
    }

def get_rebalance_dates(month_str: str, freq: str = 'weekly') -> List:
    """
    Get rebalance dates (Mondays) for a month.
    
    Args:
        month_str: YYYY-MM
        freq: 'weekly' or 'biweekly'
    """
    year, month = map(int, month_str.split('-'))
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(days=1)
    
    dates = []
    current = start
    
    # Find first Monday
    while current.weekday() != 0:  # 0=Monday
        current += timedelta(days=1)
        if current > end:
            return []
    
    # Add Mondays
    while current <= end:
        dates.append(current.date())
        if freq == 'weekly':
            current += timedelta(days=7)
        else:  # biweekly
            current += timedelta(days=14)
    
    return dates

def run_monte_carlo_for_date(
    df_intraday: pd.DataFrame,
    asof_date,
    config: Dict,
    tickers: List[str]
) -> Dict:
    """Run MC simulation for all tickers as of a specific date."""
    results = {}
    
    # Filter data up to asof_date
    asof_dt = pd.to_datetime(asof_date)
    df_window = df_intraday[df_intraday['datetime'] <= asof_dt].copy()
    
    # Get last N trading days
    trading_dates = get_last_n_trading_days(df_window, config['n_days'])
    if len(trading_dates) < config['n_days']:
        print(f"   ⚠️ Solo {len(trading_dates)} días disponibles")
    
    start_date = pd.to_datetime(trading_dates[0])
    df_filtered = df_window[df_window['datetime'].dt.date >= start_date.date()].copy()
    
    for ticker in tickers:
        ticker_data = df_filtered[df_filtered['ticker'] == ticker].sort_values('datetime')
        
        if len(ticker_data) < config['block_size']:
            results[ticker] = None
            continue
        
        sim_result = monte_carlo_simulation(
            ticker_data,
            max_hold_days=config['max_hold_days'],
            mc_paths=config['mc_paths'],
            block_size=config['block_size'],
            commission=config['commission'],
            slippage_pct=config['slippage_pct'],
            seed=config['seed'] + hash(ticker) % 1000
        )
        
        results[ticker] = sim_result
    
    return results

def run_dynamic_gate(
    intraday_parquet: str,
    month: str,
    output_dir: str,
    rebalance_freq: str = 'weekly',
    top_k: int = 4,
    max_rotation: int = 2,
    config: Dict = None
):
    """
    Run dynamic gate with weekly/biweekly rebalancing.
    
    Args:
        intraday_parquet: Path to intraday 15m data
        month: YYYY-MM
        output_dir: Output directory
        rebalance_freq: 'weekly' or 'biweekly'
        top_k: Number of tickers to select
        max_rotation: Max tickers to rotate per rebalance
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()
    
    config['top_k'] = top_k
    
    print("\n" + "="*70)
    print("🔄 DYNAMIC MONTE CARLO TICKER GATE")
    print("="*70)
    print(f"\n📋 Configuración:")
    print(f"   Mes: {month}")
    print(f"   Rebalance: {rebalance_freq}")
    print(f"   Top-K: {top_k}")
    print(f"   Max Rotation: {max_rotation}")
    print(f"   MC Paths: {config['mc_paths']}")
    
    # Get rebalance dates
    rebalance_dates = get_rebalance_dates(month, rebalance_freq)
    print(f"\n📅 Rebalances: {len(rebalance_dates)} fechas")
    for i, d in enumerate(rebalance_dates, 1):
        print(f"   {i}. {d}")
    
    # Load intraday data
    year, mon = map(int, month.split('-'))
    if mon == 12:
        last_day = 31
    else:
        last_day = (datetime(year, mon + 1, 1) - timedelta(days=1)).day
    
    month_end = f"{month}-{last_day:02d}"
    
    print(f"\n📊 Cargando datos intraday hasta {month_end}...")
    df_intraday = load_intraday_data(intraday_parquet, month_end)
    
    # Run rebalances
    rebalance_history = []
    current_portfolio = []
    
    for rebalance_idx, rebalance_date in enumerate(rebalance_dates, 1):
        print(f"\n{'='*70}")
        print(f"🔄 REBALANCE {rebalance_idx}/{len(rebalance_dates)}: {rebalance_date}")
        print(f"{'='*70}")
        
        # Run MC for all tickers
        print(f"   🔬 Simulando {len(TICKERS_UNIVERSE)} tickers...")
        results = run_monte_carlo_for_date(
            df_intraday,
            rebalance_date,
            config,
            TICKERS_UNIVERSE
        )
        
        # Rank tickers
        valid_results = {tk: res for tk, res in results.items() if res is not None}
        ranked = sorted(valid_results.items(), key=lambda x: x[1]['score'], reverse=True)
        
        # Select top-K
        new_portfolio = [tk for tk, _ in ranked[:top_k]]
        
        # Determine changes
        if rebalance_idx == 1:
            # First rebalance: select top-K
            added = new_portfolio
            dropped = []
            kept = []
        else:
            # Check rotation limits
            dropped_candidates = [tk for tk in current_portfolio if tk not in new_portfolio]
            added_candidates = [tk for tk in new_portfolio if tk not in current_portfolio]
            
            # Limit rotation
            if len(dropped_candidates) > max_rotation:
                # Keep worst performers in portfolio (don't drop all)
                dropped = dropped_candidates[:max_rotation]
                kept_from_old = dropped_candidates[max_rotation:]
                new_portfolio = [tk for tk in current_portfolio if tk not in dropped]
                # Add best new candidates
                added = added_candidates[:max_rotation]
                new_portfolio.extend(added)
                new_portfolio = new_portfolio[:top_k]  # Ensure top-K
            else:
                dropped = dropped_candidates
                added = added_candidates[:max_rotation]
                kept = [tk for tk in current_portfolio if tk not in dropped]
                new_portfolio = kept + added
                new_portfolio = new_portfolio[:top_k]
            
            kept = [tk for tk in current_portfolio if tk in new_portfolio]
        
        # Save rebalance info
        rebalance_info = {
            "rebalance_number": rebalance_idx,
            "rebalance_date": str(rebalance_date),
            "portfolio": new_portfolio,
            "changes": {
                "added": added if rebalance_idx > 1 else new_portfolio,
                "dropped": dropped,
                "kept": kept
            },
            "ranking_snapshot": [
                {
                    "rank": rank,
                    "ticker": ticker,
                    "score": metrics['score'],
                    "ev": metrics['ev'],
                    "cvar_95": metrics['cvar_95'],
                    "prob_loss": metrics['prob_loss'],
                    "tp_rate": metrics['tp_rate']
                }
                for rank, (ticker, metrics) in enumerate(ranked, 1)
            ]
        }
        
        rebalance_history.append(rebalance_info)
        current_portfolio = new_portfolio
        
        # Print summary
        print(f"\n   📊 Top-{top_k} Seleccionados:")
        for rank, ticker in enumerate(new_portfolio, 1):
            metrics = valid_results[ticker]
            print(f"      {rank}. {ticker:6s} | Score: {metrics['score']:7.4f} | EV: ${metrics['ev']:7.4f}")
        
        if rebalance_idx > 1:
            print(f"\n   🔄 Cambios:")
            if added:
                print(f"      ➕ Agregados: {', '.join(added)}")
            if dropped:
                print(f"      ➖ Eliminados: {', '.join(dropped)}")
            if not added and not dropped:
                print(f"      ✅ Sin cambios (portafolio estable)")
    
    # Save output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    gate_output = {
        "month": month,
        "generated_at": datetime.now().isoformat(),
        "config": {
            "rebalance_freq": rebalance_freq,
            "top_k": top_k,
            "max_rotation": max_rotation,
            **config
        },
        "rebalance_history": rebalance_history,
        "final_portfolio": current_portfolio,
        "total_rebalances": len(rebalance_dates)
    }
    
    gate_json = output_path / "dynamic_gate.json"
    with open(gate_json, 'w') as f:
        json.dump(gate_output, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"✅ DYNAMIC GATE COMPLETADO")
    print(f"{'='*70}")
    print(f"\n📁 Guardado: {gate_json}")
    print(f"\n🏆 Portafolio Final: {', '.join(current_portfolio)}")
    print(f"🔄 Total Rebalances: {len(rebalance_dates)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dynamic Monte Carlo Ticker Gate")
    parser.add_argument("--intraday", default="C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--output-dir", default="evidence/dynamic_gate")
    parser.add_argument("--rebalance-freq", choices=['weekly', 'biweekly'], default='weekly')
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--max-rotation", type=int, default=2, help="Max tickers to rotate per rebalance")
    parser.add_argument("--mc-paths", type=int, default=400)
    parser.add_argument("--n-days", type=int, default=20)
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config['mc_paths'] = args.mc_paths
    config['n_days'] = args.n_days
    
    run_dynamic_gate(
        args.intraday,
        args.month,
        args.output_dir,
        args.rebalance_freq,
        args.top_k,
        args.max_rotation,
        config
    )
