#!/usr/bin/env python3
"""
montecarlo_param_gate.py
Parameter Selection Engine for TP/SL optimization using Monte Carlo.

Objetivo:
  Para los tickers seleccionados (top-K), busca el mejor TP/SL dentro de rangos permitidos.
  Usa grid search + MC para encontrar combinación óptima de TP/SL.

Output:
  tp_sl_choice.json con ranking de combinaciones TP/SL y elección final.
"""

import argparse
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Configuración por defecto
DEFAULT_CONFIG = {
    "tp_range": [0.012, 0.016, 0.020, 0.024],      # [1.2%, 1.6%, 2.0%, 2.4%]
    "sl_range": [0.007, 0.010, 0.012, 0.014],      # [0.7%, 1.0%, 1.2%, 1.4%]
    "min_tp_sl_ratio": 1.3,                         # TP/SL >= 1.3
    "max_hold_days": 2,
    "mc_paths": 300,
    "block_size": 4,
    "commission": 0.0,
    "slippage_pct": 0.0001,
    "lambda_cvar": 0.5,
    "mu_loss_prob": 1.0,
    "seed": 42,
}

def load_intraday_data(parquet_path: str, asof_date: str) -> pd.DataFrame:
    """Carga datos intraday 15m hasta asof_date."""
    print(f"[INFO] Cargando datos intraday...")
    df = pd.read_parquet(parquet_path)
    
    # Timestamp handling
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
    """Retorna últimos N días hábiles."""
    dates = sorted(df['datetime'].dt.date.unique())
    return dates[-n:] if len(dates) >= n else dates

def monte_carlo_param_simulation(
    ticker_data: pd.DataFrame,
    tp_pct: float,
    sl_pct: float,
    max_hold_days: int,
    mc_paths: int,
    block_size: int,
    commission: float,
    slippage_pct: float,
    seed: int = 42
) -> Optional[Dict]:
    """
    Simula múltiples caminos con TP/SL específicos.
    Retorna métricas de score para esa combinación.
    """
    np.random.seed(seed)
    
    if len(ticker_data) < block_size * 2:
        return None
    
    bars = ticker_data.reset_index(drop=True)
    returns = (bars['close'].pct_change().fillna(0)).values
    
    n_bars = len(returns)
    n_blocks = max(1, n_bars - block_size + 1)
    blocks = [returns[i:i+block_size] for i in range(n_blocks)]
    
    pnl_array = []
    tp_count = 0
    sl_count = 0
    to_count = 0
    
    bars_per_session = 26
    max_bars = bars_per_session * max_hold_days
    
    for path_idx in range(mc_paths):
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
                pnl = (tp_price - entry_price_with_slip) * 1 - commission
                tp_count += 1
                break
            elif price <= sl_price:
                hit_bar = bar_idx
                pnl = (sl_price - entry_price_with_slip) * 1 - commission
                sl_count += 1
                break
        
        if hit_bar is None:
            exit_price = prices[-1] * (1 - slippage_pct)
            pnl = (exit_price - entry_price_with_slip) * 1 - commission
            to_count += 1
            hit_bar = len(prices) - 1
        
        pnl_array.append(pnl)
    
    pnl_array = np.array(pnl_array)
    
    # Métricas robustas
    ev = np.mean(pnl_array)
    prob_loss = np.mean(pnl_array < 0)
    
    var_95_idx = int(len(pnl_array) * 0.05)
    worst_pnls = np.sort(pnl_array)[:var_95_idx] if var_95_idx > 0 else pnl_array[pnl_array < 0]
    cvar_95 = np.mean(worst_pnls) if len(worst_pnls) > 0 else 0
    
    total_trades = mc_paths
    tp_rate = tp_count / total_trades if total_trades > 0 else 0
    sl_rate = sl_count / total_trades if total_trades > 0 else 0
    to_rate = to_count / total_trades if total_trades > 0 else 0
    
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
        'score': float(score),
    }

def run_param_gate(
    intraday_parquet: str,
    asof_date: str,
    selected_tickers: List[str],
    output_dir: str,
    config: Dict = None
) -> Dict:
    """
    Corre Param Gate: selecciona mejor TP/SL para los tickers.
    
    Returns:
        Dict con ranking de combinaciones y elección final guardados a tp_sl_choice.json
    """
    if config is None:
        config = DEFAULT_CONFIG
    
    print("\n" + "="*70)
    print("⚙️ MONTECARLO PARAM GATE (TP/SL Selection)")
    print("="*70)
    print(f"\n📋 Configuración:")
    print(f"   TP Range: {[f'{tp*100:.1f}%' for tp in config['tp_range']]}")
    print(f"   SL Range: {[f'{sl*100:.1f}%' for sl in config['sl_range']]}")
    print(f"   Min TP/SL Ratio: {config['min_tp_sl_ratio']}")
    print(f"   MC Paths: {config['mc_paths']}")
    print(f"   Selected Tickers: {selected_tickers}")
    
    # Cargar datos
    df_intraday = load_intraday_data(intraday_parquet, asof_date)
    
    # Últimos N días
    trading_dates = get_last_n_trading_days(df_intraday, 20)
    start_date = pd.to_datetime(trading_dates[0])
    df_window = df_intraday[
        (df_intraday['datetime'].dt.date >= start_date.date())
    ].copy()
    
    # Filtrar a tickers seleccionados
    df_selected = df_window[df_window['ticker'].isin(selected_tickers)].copy()
    
    if df_selected.empty:
        print("❌ Sin datos para tickers seleccionados")
        return None
    
    print(f"\n📅 Ventana: {trading_dates[0]} a {trading_dates[-1]}")
    
    # Grid search: todas las combinaciones TP/SL
    grid_results = []
    
    print(f"\n🔄 Evaluando {len(config['tp_range'])} × {len(config['sl_range'])} = {len(config['tp_range'])*len(config['sl_range'])} combinaciones...")
    print()
    
    for tp_pct in config['tp_range']:
        for sl_pct in config['sl_range']:
            # Validar constraint TP/SL ratio
            if tp_pct / sl_pct < config['min_tp_sl_ratio']:
                continue
            
            # Simular con estos parámetros
            sim_result = monte_carlo_param_simulation(
                df_selected,
                tp_pct=tp_pct,
                sl_pct=sl_pct,
                max_hold_days=config['max_hold_days'],
                mc_paths=config['mc_paths'],
                block_size=config['block_size'],
                commission=config['commission'],
                slippage_pct=config['slippage_pct'],
                seed=config['seed'] + hash((tp_pct, sl_pct)) % 1000
            )
            
            if sim_result is not None:
                grid_results.append({
                    'tp_pct': float(tp_pct),
                    'sl_pct': float(sl_pct),
                    'tp_sl_ratio': float(tp_pct / sl_pct),
                    'metrics': sim_result
                })
                
                score = sim_result['score']
                print(f"  TP={tp_pct*100:4.1f}% | SL={sl_pct*100:4.1f}% | Ratio={tp_pct/sl_pct:4.2f} | Score: {score:7.4f} ✅")
    
    # Ranking por score
    ranked = sorted(grid_results, key=lambda x: x['metrics']['score'], reverse=True)
    
    # Elegir el mejor
    if ranked:
        best = ranked[0]
        best_tp = best['tp_pct']
        best_sl = best['sl_pct']
    else:
        # Default si no hay válidos
        best_tp = 0.020
        best_sl = 0.012
        print("⚠️ No hay combinaciones válidas, usando defaults: TP=2.0%, SL=1.2%")
    
    print(f"\n" + "="*70)
    print(f"🏆 PARÁMETROS SELECCIONADOS")
    print(f"="*70)
    print(f"\nTP: {best_tp*100:.1f}% | SL: {best_sl*100:.1f}% | TP/SL Ratio: {best_tp/best_sl:.2f}")
    
    if ranked:
        metrics = ranked[0]['metrics']
        print(f"\nMétricas esperadas:")
        print(f"  EV:        ${metrics['ev']:.4f}")
        print(f"  CVaR 95%:  ${metrics['cvar_95']:.4f}")
        print(f"  P(loss):   {metrics['prob_loss']:.2%}")
        print(f"  Score:     {metrics['score']:.4f}")
        print(f"  Rates:     TP {metrics['tp_rate']:.1%} | SL {metrics['sl_rate']:.1%} | TO {metrics['to_rate']:.1%}")
    
    # Guardar output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    param_output = {
        "asof_date": asof_date,
        "generated_at": datetime.now().isoformat(),
        "config": config,
        "selected_tickers": selected_tickers,
        "grid_results": ranked,
        "final_choice": {
            "tp_pct": best_tp,
            "sl_pct": best_sl,
            "tp_sl_ratio": best_tp / best_sl if best_sl != 0 else 0,
            "rank_position": 1 if ranked and ranked[0]['tp_pct'] == best_tp else None
        }
    }
    
    param_json = output_path / "tp_sl_choice.json"
    with open(param_json, 'w') as f:
        json.dump(param_output, f, indent=2)
    
    print(f"\n✅ Guardado: {param_json}")
    
    return param_output

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monte Carlo TP/SL Parameter Selection")
    parser.add_argument("--intraday", default="C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")
    parser.add_argument("--asof-date", default="2025-03-31")
    parser.add_argument("--tickers", default="CVX,XOM,PFE,NVDA", help="Comma-separated ticker list")
    parser.add_argument("--output-dir", default="evidence/param_gate")
    parser.add_argument("--mc-paths", type=int, default=300)
    
    args = parser.parse_args()
    
    selected_tickers = [t.strip() for t in args.tickers.split(',')]
    
    config = DEFAULT_CONFIG.copy()
    config['mc_paths'] = args.mc_paths
    
    result = run_param_gate(
        args.intraday,
        args.asof_date,
        selected_tickers,
        args.output_dir,
        config
    )
    
    print("\n" + "="*70)
    print("✅ PARAM GATE COMPLETADO")
    print("="*70)
