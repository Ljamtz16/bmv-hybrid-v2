#!/usr/bin/env python3
"""
Comparación 3 versiones: V1 (baseline) vs V2 (strict) vs V2 (balanced)
"""

import pandas as pd
import json
from pathlib import Path


def normalize_summary(summary):
    """Normaliza formato de summary.json."""
    if 'config' in summary and 'results' in summary:
        return summary
    
    capital = 600
    results = summary.copy()
    
    if 'roi_pct' not in results:
        results['roi_pct'] = (results['total_pnl'] / capital) * 100
    
    if 'avg_win' not in results and 'gross_profit' in results and 'win_count' in results:
        results['avg_win'] = results['gross_profit'] / results['win_count'] if results['win_count'] > 0 else 0
    
    if 'avg_loss' not in results and 'gross_loss' in results and 'loss_count' in results:
        results['avg_loss'] = -results['gross_loss'] / results['loss_count'] if results['loss_count'] > 0 else 0
    
    if 'wins' not in results:
        results['wins'] = results.get('win_count', 0)
    
    if 'losses' not in results:
        results['losses'] = results.get('loss_count', 0)
    
    return {
        'config': {'capital': capital, 'tp_pct': 0.016, 'sl_pct': 0.01},
        'results': results
    }


def load_simulation(output_dir):
    """Carga all_trades.csv y summary.json."""
    trades_path = Path(output_dir) / 'all_trades.csv'
    summary_path = Path(output_dir) / 'summary.json'
    
    if not trades_path.exists():
        return None, None
    
    trades = pd.read_csv(trades_path)
    
    with open(summary_path, 'r') as f:
        summary = json.load(f)
    
    summary = normalize_summary(summary)
    
    return trades, summary


def print_comparison():
    print("\n" + "="*100)
    print("COMPARACIÓN 3 VERSIONES: INTRADAY V1 (baseline) vs V2 (strict) vs V2 (balanced)")
    print("="*100)
    
    # V1: Baseline (sin filtros)
    v1_trades, v1_summary = load_simulation('evidence/paper_2022_2025_intraday_600_tp1p6_sl1')
    
    # V2 Strict: Filtros muy estrictos
    v2s_trades, v2s_summary = load_simulation('evidence/paper_2022_2025_intraday_v2_strict')
    
    # V2 Balanced: Filtros semi-estrictos
    v2b_trades, v2b_summary = load_simulation('evidence/paper_2022_2025_intraday_v2_balanced')
    
    if v1_trades is None or v2s_trades is None or v2b_trades is None:
        print("[ERROR] No se encontraron algunos archivos")
        return
    
    print("\n📊 CONFIGURACIÓN")
    print("-" * 100)
    print(f"{'':25} {'V1 (Baseline)':>23} {'V2 (Strict)':>23} {'V2 (Balanced)':>23}")
    print("-" * 100)
    print(f"{'Filtros':25} {'prob_win>0.5':>23} {'prob_win>0.58+régimen':>23} {'prob_win>0.55+régimen':>23}")
    print(f"{'Ventanas horarias':25} {'Todas (sin filtro)':>23} {'2 ventanas':>23} {'3 ventanas':>23}")
    print(f"{'Max trades/ventana':25} {'Ilimitado':>23} {'3':>23} {'5':>23}")
    print(f"{'Position Size':25} {'10%':>23} {'30%':>23} {'25%':>23}")
    print(f"{'TP/SL':25} {'Fijo 1.6%/1%':>23} {'1.5x/0.75x ATR':>23} {'1.5x/0.75x ATR':>23}")
    
    print("\n💰 RESULTADOS CLAVE")
    print("-" * 100)
    print(f"{'':25} {'V1 (Baseline)':>23} {'V2 (Strict)':>23} {'V2 (Balanced)':>23}")
    print("-" * 100)
    
    v1_pnl = v1_summary['results']['total_pnl']
    v2s_pnl = v2s_summary['results']['total_pnl']
    v2b_pnl = v2b_summary['results']['total_pnl']
    print(f"{'Total P&L':25} ${v1_pnl:>22,.2f} ${v2s_pnl:>22,.2f} ${v2b_pnl:>22,.2f}")
    
    v1_roi = v1_summary['results']['roi_pct']
    v2s_roi = v2s_summary['results']['roi_pct']
    v2b_roi = v2b_summary['results']['roi_pct']
    print(f"{'ROI':25} {f'{v1_roi:>21.2f}%'} {f'{v2s_roi:>21.2f}%'} {f'{v2b_roi:>21.2f}%'}")
    
    v1_trades_count = v1_summary['results']['total_trades']
    v2s_trades_count = v2s_summary['results']['total_trades']
    v2b_trades_count = v2b_summary['results']['total_trades']
    print(f"{'Total Trades':25} {v1_trades_count:>23,} {v2s_trades_count:>23,} {v2b_trades_count:>23,}")
    
    v1_pf = v1_summary['results']['profit_factor']
    v2s_pf = v2s_summary['results']['profit_factor']
    v2b_pf = v2b_summary['results']['profit_factor']
    print(f"{'Profit Factor':25} {f'{v1_pf:>22.2f}x'} {f'{v2s_pf:>22.2f}x'} {f'{v2b_pf:>22.2f}x'}")
    
    v1_wr = v1_summary['results']['win_rate_pct']
    v2s_wr = v2s_summary['results']['win_rate_pct']
    v2b_wr = v2b_summary['results']['win_rate_pct']
    print(f"{'Win Rate':25} {f'{v1_wr:>21.1f}%'} {f'{v2s_wr:>21.1f}%'} {f'{v2b_wr:>21.1f}%'}")
    
    print("\n📈 COMPARACIÓN VS BASELINE (V1)")
    print("-" * 100)
    print(f"{'':25} {'V2 Strict vs V1':>40} {'V2 Balanced vs V1':>30}")
    print("-" * 100)
    
    # Delta P&L
    delta_s = v2s_pnl - v1_pnl
    delta_b = v2b_pnl - v1_pnl
    print(f"{'Delta P&L':25} ${delta_s:>39,.2f} ${delta_b:>29,.2f}")
    
    # Delta ROI
    delta_roi_s = v2s_roi - v1_roi
    delta_roi_b = v2b_roi - v1_roi
    print(f"{'Delta ROI':25} {f'{delta_roi_s:>38.2f} pp'} {f'{delta_roi_b:>28.2f} pp'}")
    
    # Reducción trades
    red_s = (1 - v2s_trades_count / v1_trades_count) * 100 if v1_trades_count > 0 else 0
    red_b = (1 - v2b_trades_count / v1_trades_count) * 100 if v1_trades_count > 0 else 0
    print(f"{'Reducción trades':25} {f'-{red_s:.2f}%':>40} {f'-{red_b:.2f}%':>30}")
    
    # Delta PF
    delta_pf_s = v2s_pf - v1_pf
    delta_pf_b = v2b_pf - v1_pf
    print(f"{'Delta PF':25} {f'+{delta_pf_s:.2f}x':>40} {f'+{delta_pf_b:.2f}x':>30}")
    
    print("\n🎯 CUMPLIMIENTO OBJETIVO (PF ≥ 1.15x)")
    print("-" * 100)
    
    status_v1 = "❌ NO" if v1_pf < 1.15 else "✅ SÍ"
    status_v2s = "❌ NO" if v2s_pf < 1.15 else "✅ SÍ"
    status_v2b = "❌ NO" if v2b_pf < 1.15 else "✅ SÍ"
    
    print(f"{'V1 (Baseline)':25} {status_v1:>23} (PF {v1_pf:.2f}x)")
    print(f"{'V2 (Strict)':25} {status_v2s:>23} (PF {v2s_pf:.2f}x)")
    print(f"{'V2 (Balanced)':25} {status_v2b:>23} (PF {v2b_pf:.2f}x)")
    
    print("\n💡 ANÁLISIS")
    print("-" * 100)
    
    print("\n📊 Trade-off Calidad vs Cantidad:")
    print(f"  V2 Strict:   {v2s_trades_count:3} trades | PF {v2s_pf:.2f}x | ROI {v2s_roi:+.2f}% | ⚠️  Muestra muy pequeña")
    print(f"  V2 Balanced: {v2b_trades_count:3} trades | PF {v2b_pf:.2f}x | ROI {v2b_roi:+.2f}% | ✅ Balance óptimo")
    
    print("\n🎯 Recomendación:")
    if v2b_pf >= 1.15 and v2b_trades_count >= 30:
        print("  ✅ V2 Balanced es la mejor opción:")
        print(f"     - Cumple objetivo PF ≥ 1.15x (actual: {v2b_pf:.2f}x)")
        print(f"     - Suficientes trades para validación ({v2b_trades_count})")
        print(f"     - ROI positivo ({v2b_roi:+.2f}%)")
    else:
        print("  ⚠️  Ambas versiones V2 tienen limitaciones:")
        print("     - Considerar ampliar período de backtest")
        print("     - O relajar más filtros (prob_win > 0.53)")
    
    print("\n⚠️  IMPORTANTE:")
    print(f"  - V2 Balanced tiene {v2b_trades_count} trades en 4 años = {v2b_trades_count/1460:.2f} trades/día")
    print(f"  - Para estrategia intraday, esto es MUY selectivo")
    print(f"  - En producción, podrías ver semanas sin trades")
    
    print("\n" + "="*100)


if __name__ == '__main__':
    print_comparison()
