#!/usr/bin/env python3
"""
hybrid_score_gate.py
Hybrid Ticker Gate: Monte Carlo (60%) + Signal Quality (40%)

Fase 3: Combina score MC histórico con calidad de señales actuales.
Evita tickers "estadísticamente buenos pero sin buenos setups actuales".

Usage:
    python hybrid_score_gate.py --asof-date 2025-03-31 --forecast data/daily/signals_with_gates.parquet
"""

import argparse
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

# Configuración
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
    "mc_weight": 0.6,
    "signal_weight": 0.4,
    "signal_lookback": 10,  # días para evaluar señales
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

def load_forecast_data(parquet_path: str, asof_date: str) -> pd.DataFrame:
    """Carga forecast con prob_win hasta asof_date."""
    df = pd.read_parquet(parquet_path)
    
    # Detectar columna de fecha
    date_col = None
    for col in ['date', 'Date', 'forecast_date', 'asof_date', 'datetime']:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        raise ValueError("No se encontró columna de fecha en forecast")
    
    df['date'] = pd.to_datetime(df[date_col])
    
    asof_dt = pd.to_datetime(asof_date)
    df = df[df['date'] <= asof_dt]
    
    # Verificar columnas necesarias
    if 'prob_win' not in df.columns:
        raise ValueError("Forecast debe tener columna 'prob_win'")
    if 'ticker' not in df.columns:
        raise ValueError("Forecast debe tener columna 'ticker'")
    
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

def compute_signal_quality_score(
    forecast_df: pd.DataFrame,
    ticker: str,
    asof_date: str,
    lookback_days: int = 10
) -> Dict:
    """
    Calcula score de calidad de señales para un ticker.
    
    Métricas:
    - Mean prob_win: promedio de probabilidades (>0.5 es bueno)
    - Signal count: número de señales (más oportunidades = mejor)
    - Consistency: desviación estándar baja = señales consistentes
    - Recency: señales de últimos 3 días pesan más
    
    Returns:
        Dict con signal_quality_score y métricas
    """
    asof_dt = pd.to_datetime(asof_date)
    start_dt = asof_dt - timedelta(days=lookback_days)
    
    # Filtrar señales del ticker en ventana
    ticker_signals = forecast_df[
        (forecast_df['ticker'] == ticker) &
        (forecast_df['date'] >= start_dt) &
        (forecast_df['date'] <= asof_dt)
    ].copy()
    
    if len(ticker_signals) == 0:
        return {
            'signal_quality_score': 0.0,
            'n_signals': 0,
            'mean_prob_win': 0.5,
            'std_prob_win': 0.0,
            'recent_prob_win': 0.5
        }
    
    # Métricas
    prob_wins = ticker_signals['prob_win'].values
    n_signals = len(prob_wins)
    mean_prob = np.mean(prob_wins)
    std_prob = np.std(prob_wins) if n_signals > 1 else 0.0
    
    # Recency: últimos 3 días
    recent_cutoff = asof_dt - timedelta(days=3)
    recent_signals = ticker_signals[ticker_signals['date'] >= recent_cutoff]
    recent_prob = np.mean(recent_signals['prob_win'].values) if len(recent_signals) > 0 else mean_prob
    
    # Score compuesto
    # 1. Mean prob_win normalizado: (mean - 0.5) * 2 → [-1, 1]
    prob_component = (mean_prob - 0.5) * 2
    
    # 2. Signal count: más señales = mejor (cap at 10 signals)
    count_component = min(n_signals / 10, 1.0)
    
    # 3. Consistency: menor std = mejor
    consistency_component = 1 - min(std_prob * 4, 1.0)
    
    # 4. Recency weight
    recency_component = (recent_prob - 0.5) * 2
    
    # Weighted average
    signal_quality_score = (
        0.50 * prob_component +
        0.20 * count_component +
        0.15 * consistency_component +
        0.15 * recency_component
    )
    
    return {
        'signal_quality_score': float(signal_quality_score),
        'n_signals': int(n_signals),
        'mean_prob_win': float(mean_prob),
        'std_prob_win': float(std_prob),
        'recent_prob_win': float(recent_prob)
    }

def run_hybrid_gate(
    intraday_parquet: str,
    forecast_parquet: str,
    asof_date: str,
    output_dir: str,
    config: Dict = None
):
    """
    Run Hybrid Ticker Gate: MC (60%) + Signal Quality (40%)
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()
    
    print("\n" + "="*70)
    print("🎯 HYBRID MONTE CARLO + SIGNAL QUALITY GATE")
    print("="*70)
    print(f"\n📋 Configuración:")
    print(f"   MC Weight: {config['mc_weight']:.1%}")
    print(f"   Signal Weight: {config['signal_weight']:.1%}")
    print(f"   MC Window: {config['n_days']} días")
    print(f"   Signal Lookback: {config['signal_lookback']} días")
    print(f"   Top-K: {config['top_k']}")
    
    # Cargar datos
    print(f"\n📊 Cargando datos...")
    df_intraday = load_intraday_data(intraday_parquet, asof_date)
    df_forecast = load_forecast_data(forecast_parquet, asof_date)
    
    print(f"   Intraday: {len(df_intraday)} barras")
    print(f"   Forecast: {len(df_forecast)} señales")
    
    # Get last N trading days for MC
    trading_dates = get_last_n_trading_days(df_intraday, config['n_days'])
    start_date = pd.to_datetime(trading_dates[0])
    df_window = df_intraday[df_intraday['datetime'].dt.date >= start_date.date()].copy()
    
    print(f"\n🔬 Calculando scores para {len(TICKERS_UNIVERSE)} tickers...")
    
    results = {}
    
    for ticker in TICKERS_UNIVERSE:
        print(f"\n   {ticker}:")
        
        # 1. Monte Carlo Score
        ticker_data = df_window[df_window['ticker'] == ticker].sort_values('datetime')
        
        if len(ticker_data) < config['block_size']:
            print(f"      ❌ Datos intraday insuficientes")
            results[ticker] = None
            continue
        
        mc_result = monte_carlo_simulation(
            ticker_data,
            max_hold_days=config['max_hold_days'],
            mc_paths=config['mc_paths'],
            block_size=config['block_size'],
            commission=config['commission'],
            slippage_pct=config['slippage_pct'],
            seed=config['seed'] + hash(ticker) % 1000
        )
        
        if mc_result is None:
            print(f"      ❌ Simulación MC falló")
            results[ticker] = None
            continue
        
        print(f"      MC Score: {mc_result['score']:7.4f} | EV: ${mc_result['ev']:6.4f}")
        
        # 2. Signal Quality Score
        signal_result = compute_signal_quality_score(
            df_forecast,
            ticker,
            asof_date,
            config['signal_lookback']
        )
        
        print(f"      Signal Score: {signal_result['signal_quality_score']:7.4f} | Signals: {signal_result['n_signals']} | Mean P(win): {signal_result['mean_prob_win']:.3f}")
        
        # 3. Normalize and combine
        results[ticker] = {
            'mc_score': mc_result['score'],
            'signal_quality_score': signal_result['signal_quality_score'],
            'mc_metrics': mc_result,
            'signal_metrics': signal_result
        }
    
    # Normalize scores to [0, 1]
    valid_results = {tk: res for tk, res in results.items() if res is not None}
    
    if not valid_results:
        print("\n❌ No hay resultados válidos")
        return
    
    # MC scores normalization
    mc_scores = [res['mc_score'] for res in valid_results.values()]
    mc_min, mc_max = min(mc_scores), max(mc_scores)
    mc_range = mc_max - mc_min if mc_max > mc_min else 1.0
    
    # Signal scores normalization
    signal_scores = [res['signal_quality_score'] for res in valid_results.values()]
    signal_min, signal_max = min(signal_scores), max(signal_scores)
    signal_range = signal_max - signal_min if signal_max > signal_min else 1.0
    
    # Compute hybrid scores
    for ticker, res in valid_results.items():
        mc_normalized = (res['mc_score'] - mc_min) / mc_range
        signal_normalized = (res['signal_quality_score'] - signal_min) / signal_range
        
        hybrid_score = (
            config['mc_weight'] * mc_normalized +
            config['signal_weight'] * signal_normalized
        )
        
        res['mc_normalized'] = mc_normalized
        res['signal_normalized'] = signal_normalized
        res['hybrid_score'] = hybrid_score
    
    # Rank by hybrid score
    ranked = sorted(valid_results.items(), key=lambda x: x[1]['hybrid_score'], reverse=True)
    
    top_k_tickers = [tk for tk, _ in ranked[:config['top_k']]]
    
    print(f"\n{'='*70}")
    print(f"🏆 TOP-{config['top_k']} HYBRID RANKING")
    print(f"{'='*70}")
    
    for rank, (ticker, res) in enumerate(ranked[:config['top_k']], 1):
        print(f"\n{rank}. {ticker}")
        print(f"   Hybrid Score:  {res['hybrid_score']:.4f}")
        print(f"   MC (norm):     {res['mc_normalized']:.4f}  (raw: {res['mc_score']:.4f})")
        print(f"   Signal (norm): {res['signal_normalized']:.4f}  (raw: {res['signal_quality_score']:.4f})")
        print(f"   Signals: {res['signal_metrics']['n_signals']} | P(win): {res['signal_metrics']['mean_prob_win']:.3f}")
    
    # Save output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    gate_output = {
        "asof_date": asof_date,
        "generated_at": datetime.now().isoformat(),
        "config": config,
        "ranking": [
            {
                "rank": rank,
                "ticker": ticker,
                "hybrid_score": res['hybrid_score'],
                "mc_score": res['mc_score'],
                "mc_normalized": res['mc_normalized'],
                "signal_quality_score": res['signal_quality_score'],
                "signal_normalized": res['signal_normalized'],
                "mc_metrics": res['mc_metrics'],
                "signal_metrics": res['signal_metrics']
            }
            for rank, (ticker, res) in enumerate(ranked, 1)
        ],
        "selected_tickers": top_k_tickers
    }
    
    gate_json = output_path / "hybrid_gate.json"
    with open(gate_json, 'w') as f:
        json.dump(gate_output, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"✅ HYBRID GATE COMPLETADO")
    print(f"{'='*70}")
    print(f"\n📁 Guardado: {gate_json}")
    print(f"\n🏆 Tickers Seleccionados: {', '.join(top_k_tickers)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid Monte Carlo + Signal Quality Gate")
    parser.add_argument("--intraday", default="C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")
    parser.add_argument("--forecast", default="data/daily/signals_with_gates.parquet")
    parser.add_argument("--asof-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output-dir", default="evidence/hybrid_gate")
    parser.add_argument("--mc-weight", type=float, default=0.6)
    parser.add_argument("--signal-weight", type=float, default=0.4)
    parser.add_argument("--signal-lookback", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--mc-paths", type=int, default=400)
    parser.add_argument("--n-days", type=int, default=20)
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config['mc_weight'] = args.mc_weight
    config['signal_weight'] = args.signal_weight
    config['signal_lookback'] = args.signal_lookback
    config['top_k'] = args.top_k
    config['mc_paths'] = args.mc_paths
    config['n_days'] = args.n_days
    
    run_hybrid_gate(
        args.intraday,
        args.forecast,
        args.asof_date,
        args.output_dir,
        config
    )
