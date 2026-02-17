#!/usr/bin/env python3
"""
montecarlo_gate.py
Ticker Selection Engine using Monte Carlo simulation with block bootstrap.

Objetivo:
  Para cada ticker, simula múltiples caminos de precio re-muestreando bloques 15m.
  Calcula score robusto (EV - λ·CVaR - μ·P(loss)).
  Selecciona top-K tickers con mejor score.

Output:
  ticker_gate.json con ranking y métricas de cada ticker.
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
    "n_days": 20,              # Ventana histórica en días hábiles
    "max_hold_days": 2,        # Máximo hold en sesiones
    "mc_paths": 400,           # Número de caminos MC
    "block_size": 4,           # Barras 15m por bloque (~1 hora)
    "top_k": 4,                # Cantidad de tickers a seleccionar
    "commission": 0.0,         # Comisión por trade (round-trip)
    "slippage_pct": 0.0001,    # Slippage como % (0.01%)
    "lambda_cvar": 0.5,        # Penalidad CVaR en score
    "mu_loss_prob": 1.0,       # Penalidad P(loss) en score
    "seed": 42,                # Para reproducibilidad
}

def load_intraday_data(parquet_path: str, asof_date: str) -> pd.DataFrame:
    """
    Carga datos intraday 15m hasta asof_date.
    Retorna DataFrame con columnas: datetime, ticker, open, high, low, close, volume.
    """
    print(f"[INFO] Cargando datos intraday desde {parquet_path}...")
    df = pd.read_parquet(parquet_path)
    
    # Renombrar columna de datetime si es necesario
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], utc=False)
    elif df.columns[0] in ['timestamp', 'datetime']:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    else:
        df['datetime'] = pd.to_datetime(df.iloc[:, 0], utc=False)
    
    # Remover timezone info si existe
    if df['datetime'].dt.tz is not None:
        df['datetime'] = df['datetime'].dt.tz_localize(None)
    
    # Filtrar hasta asof_date
    asof_dt = pd.to_datetime(asof_date)
    df = df[df['datetime'] <= asof_dt]
    
    print(f"  Total rows: {len(df)}")
    print(f"  Tickers: {sorted(df['ticker'].unique())}")
    print(f"  Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    
    return df

def get_last_n_trading_days(df: pd.DataFrame, n: int) -> List[pd.Timestamp]:
    """
    Retorna los últimos N días hábiles únicos en el dataset.
    """
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
) -> Dict[str, any]:
    """
    Simula múltiples caminos de precio para un ticker.
    
    Retorna:
    {
        'pnl_array': array de PnLs simulados,
        'ev': expectancia,
        'cvar_95': valor en riesgo condicional 95%,
        'prob_loss': probabilidad de pérdida,
        'tp_rate': tasa de TP hits,
        'sl_rate': tasa de SL hits,
        'to_rate': tasa de timeouts,
        'avg_hold_bars': promedio de barras en hold,
        'score': score final
    }
    """
    np.random.seed(seed)
    
    if len(ticker_data) < block_size * 2:
        return None  # Datos insuficientes
    
    # Preparar retornos en bloques
    bars = ticker_data.reset_index(drop=True)
    returns = (bars['close'].pct_change().fillna(0)).values
    
    # Crear bloques
    n_bars = len(returns)
    n_blocks = max(1, n_bars - block_size + 1)
    blocks = [returns[i:i+block_size] for i in range(n_blocks)]
    
    # Parámetros de entrada/salida (default)
    # TP: 2.0%, SL: 1.2%, entrada: open, salida: intraday en max_hold_days
    tp_pct = 0.020
    sl_pct = 0.012
    
    pnl_array = []
    tp_count = 0
    sl_count = 0
    to_count = 0
    hold_bars_list = []
    
    # Número de barras por sesión (aprox 26 para 15m × 6.5 horas)
    bars_per_session = 26
    max_bars = bars_per_session * max_hold_days
    
    for path_idx in range(mc_paths):
        # Resample bloques para crear un camino sintético
        path_idx_start = np.random.randint(0, len(returns) - bars_per_session)
        simulated_returns = np.concatenate([
            blocks[np.random.randint(0, len(blocks))]
            for _ in range(max(1, max_bars // block_size + 1))
        ])[:max_bars]
        
        # Simular precio (partiendo de último close)
        last_price = bars['close'].iloc[-1]
        entry_price = last_price
        
        cumsum_returns = np.cumsum(simulated_returns)
        prices = entry_price * (1 + cumsum_returns)
        
        # Aplicar slippage a entrada
        entry_price_with_slip = entry_price * (1 + slippage_pct)
        
        # Buscar TP, SL o TO
        tp_price = entry_price_with_slip * (1 + tp_pct)
        sl_price = entry_price_with_slip * (1 - sl_pct)
        
        hit_bar = None
        for bar_idx, price in enumerate(prices):
            if price >= tp_price:
                hit_bar = bar_idx
                pnl = (tp_price - entry_price_with_slip) * 1 - commission
                tp_count += 1
                break
            elif price <= sl_price:
                hit_bar = bar_idx
                pnl = (sl_price - entry_price_with_slip) * 1 - commission
                sl_count += 1
                break
        
        if hit_bar is None:
            # Timeout: sale al final al último precio
            exit_price = prices[-1] * (1 - slippage_pct)  # Slippage al salir
            pnl = (exit_price - entry_price_with_slip) * 1 - commission
            to_count += 1
            hit_bar = len(prices) - 1
        
        pnl_array.append(pnl)
        hold_bars_list.append(hit_bar)
    
    pnl_array = np.array(pnl_array)
    
    # Calcular métricas robustas
    ev = np.mean(pnl_array)
    prob_loss = np.mean(pnl_array < 0)
    
    # CVaR 95%: pérdida promedio del peor 5%
    var_95_idx = int(len(pnl_array) * 0.05)
    worst_pnls = np.sort(pnl_array)[:var_95_idx] if var_95_idx > 0 else pnl_array[pnl_array < 0]
    cvar_95 = np.mean(worst_pnls) if len(worst_pnls) > 0 else 0
    
    # Rates
    total_trades = mc_paths
    tp_rate = tp_count / total_trades if total_trades > 0 else 0
    sl_rate = sl_count / total_trades if total_trades > 0 else 0
    to_rate = to_count / total_trades if total_trades > 0 else 0
    
    avg_hold_bars = np.mean(hold_bars_list)
    
    # Score robusto
    lambda_cvar = DEFAULT_CONFIG["lambda_cvar"]
    mu_loss_prob = DEFAULT_CONFIG["mu_loss_prob"]
    score = ev - lambda_cvar * abs(cvar_95) - mu_loss_prob * prob_loss
    
    return {
        'pnl_array': pnl_array.tolist(),
        'ev': float(ev),
        'cvar_95': float(cvar_95),
        'prob_loss': float(prob_loss),
        'tp_rate': float(tp_rate),
        'sl_rate': float(sl_rate),
        'to_rate': float(to_rate),
        'avg_hold_bars': float(avg_hold_bars),
        'score': float(score),
    }

def run_ticker_gate(
    intraday_parquet: str,
    asof_date: str,
    output_dir: str,
    config: Dict = None
) -> Dict:
    """
    Corre Ticker Gate: selecciona top-K tickers con mejor score.
    
    Returns:
        Dict con ranking y métricas guardadas a ticker_gate.json
    """
    if config is None:
        config = DEFAULT_CONFIG
    
    print("\n" + "="*70)
    print("🎯 MONTECARLO TICKER GATE")
    print("="*70)
    print(f"\n📋 Configuración:")
    print(f"   Ventana: {config['n_days']} días hábiles")
    print(f"   MC Paths: {config['mc_paths']}")
    print(f"   Block Size: {config['block_size']} barras")
    print(f"   Top-K: {config['top_k']}")
    print(f"   λ (CVaR): {config['lambda_cvar']}")
    print(f"   μ (P(loss)): {config['mu_loss_prob']}")
    
    # Cargar datos
    df_intraday = load_intraday_data(intraday_parquet, asof_date)
    
    # Obtener últimos N días hábiles
    trading_dates = get_last_n_trading_days(df_intraday, config['n_days'])
    print(f"\n📅 Últimos {len(trading_dates)} días hábiles: {trading_dates[0]} a {trading_dates[-1]}")
    
    # Filtrar a datos en esa ventana
    start_date = pd.to_datetime(trading_dates[0])
    df_window = df_intraday[
        (df_intraday['datetime'].dt.date >= start_date.date())
    ].copy()
    
    # Correr MC para cada ticker
    results = {}
    tickers = sorted(df_window['ticker'].unique())
    
    print(f"\n🔄 Simulando {len(tickers)} tickers...")
    for ticker in tickers:
        print(f"   {ticker}...", end=" ", flush=True)
        ticker_data = df_window[df_window['ticker'] == ticker].sort_values('datetime')
        
        if len(ticker_data) < config['block_size']:
            print("❌ Datos insuficientes")
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
        
        if sim_result is None:
            print("❌ Simulación falló")
            results[ticker] = None
        else:
            results[ticker] = sim_result
            print(f"✅ Score: {sim_result['score']:.4f}")
    
    # Seleccionar top-K
    valid_results = {tk: res for tk, res in results.items() if res is not None}
    ranked = sorted(valid_results.items(), key=lambda x: x[1]['score'], reverse=True)
    
    top_k_tickers = [tk for tk, _ in ranked[:config['top_k']]]
    
    print(f"\n{'='*70}")
    print(f"🏆 TOP-{config['top_k']} SELECCIONADOS")
    print(f"{'='*70}")
    for rank, (ticker, metrics) in enumerate(ranked[:config['top_k']], 1):
        print(f"\n{rank}. {ticker}")
        print(f"   EV:        ${metrics['ev']:.4f}")
        print(f"   CVaR 95%:  ${metrics['cvar_95']:.4f}")
        print(f"   P(loss):   {metrics['prob_loss']:.2%}")
        print(f"   Score:     {metrics['score']:.4f}")
        print(f"   Rates:     TP {metrics['tp_rate']:.1%} | SL {metrics['sl_rate']:.1%} | TO {metrics['to_rate']:.1%}")
    
    # Guardar output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    gate_output = {
        "asof_date": asof_date,
        "generated_at": datetime.now().isoformat(),
        "config": config,
        "window_dates": {
            "start": str(trading_dates[0]),
            "end": str(trading_dates[-1])
        },
        "ranking": [
            {
                "rank": rank,
                "ticker": ticker,
                "metrics": metrics
            }
            for rank, (ticker, metrics) in enumerate(ranked, 1)
        ],
        "selected_tickers": top_k_tickers,
        "all_results": valid_results
    }
    
    gate_json = output_path / "ticker_gate.json"
    with open(gate_json, 'w') as f:
        json.dump(gate_output, f, indent=2)
    
    print(f"\n✅ Guardado: {gate_json}")
    
    return gate_output

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monte Carlo Ticker Selection Gate")
    parser.add_argument("--intraday", default="C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")
    parser.add_argument("--asof-date", default="2025-03-31")
    parser.add_argument("--output-dir", default="evidence/ticker_gate")
    parser.add_argument("--n-days", type=int, default=20)
    parser.add_argument("--mc-paths", type=int, default=400)
    parser.add_argument("--top-k", type=int, default=4)
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config['n_days'] = args.n_days
    config['mc_paths'] = args.mc_paths
    config['top_k'] = args.top_k
    
    result = run_ticker_gate(
        args.intraday,
        args.asof_date,
        args.output_dir,
        config
    )
    
    print("\n" + "="*70)
    print("✅ TICKER GATE COMPLETADO")
    print("="*70)
