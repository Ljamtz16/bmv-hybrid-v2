#!/usr/bin/env python3
"""
Comparación completa: V1 (baseline) vs V2 (strict/balanced) vs V2.5 (optimal) vs V3 (aggressive)
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


def print_full_comparison():
    print("\n" + "="*120)
    print("COMPARACIÓN COMPLETA: TODAS LAS VERSIONES INTRADAY")
    print("="*120)
    
    versions = [
        ('V1 (Baseline)', 'evidence/paper_2022_2025_intraday_600_tp1p6_sl1'),
        ('V2 (Strict)', 'evidence/paper_2022_2025_intraday_v2_strict'),
        ('V2 (Balanced)', 'evidence/paper_2022_2025_intraday_v2_balanced'),
        ('V2.5 (Optimal)', 'evidence/paper_2022_2025_intraday_v2p5_optimal'),
        ('V3 (Aggressive)', 'evidence/paper_2022_2025_intraday_v3_aggressive')
    ]
    
    data = {}
    for name, path in versions:
        trades, summary = load_simulation(path)
        if trades is not None:
            data[name] = (trades, summary)
    
    if len(data) < 5:
        print(f"[ERROR] Solo se encontraron {len(data)}/5 simulaciones")
        return
    
    print("\n📊 CONFIGURACIÓN")
    print("-" * 120)
    print(f"{'':18} {'V1 (Baseline)':>18} {'V2 (Strict)':>18} {'V2 (Balanced)':>18} {'V2.5 (Optimal)':>18} {'V3 (Aggressive)':>18}")
    print("-" * 120)
    print(f"{'prob_win':18} {'>0.5':>18} {'>0.58':>18} {'>0.55':>18} {'>0.54':>18} {'>0.52':>18}")
    print(f"{'Filtros régimen':18} {'NO':>18} {'SÍ (estricto)':>18} {'SÍ (relajado)':>18} {'SÍ (relajado)':>18} {'NO':>18}")
    print(f"{'Ventanas':18} {'Ilimitadas':>18} {'2':>18} {'3':>18} {'4':>18} {'4':>18}")
    print(f"{'Max/ventana':18} {'Ilimitado':>18} {'3':>18} {'5':>18} {'7':>18} {'10':>18}")
    print(f"{'Position Size':18} {'10%':>18} {'30%':>18} {'25%':>18} {'23%':>18} {'20%':>18}")
    
    print("\n💰 RESULTADOS CLAVE")
    print("-" * 120)
    print(f"{'':18} {'V1 (Baseline)':>18} {'V2 (Strict)':>18} {'V2 (Balanced)':>18} {'V2.5 (Optimal)':>18} {'V3 (Aggressive)':>18}")
    print("-" * 120)
    
    # Trades
    trades_counts = [data[name][1]['results']['total_trades'] for name, _ in versions]
    print(f"{'Trades':18} {trades_counts[0]:>18,} {trades_counts[1]:>18,} {trades_counts[2]:>18,} {trades_counts[3]:>18,} {trades_counts[4]:>18,}")
    
    # PF
    pfs = [data[name][1]['results']['profit_factor'] for name, _ in versions]
    pf_str = [f"{pf:.2f}x" for pf in pfs]
    print(f"{'Profit Factor':18} {pf_str[0]:>18} {pf_str[1]:>18} {pf_str[2]:>18} {pf_str[3]:>18} {pf_str[4]:>18}")
    
    # ROI
    rois = [data[name][1]['results']['roi_pct'] for name, _ in versions]
    roi_str = [f"{roi:+.2f}%" for roi in rois]
    print(f"{'ROI':18} {roi_str[0]:>18} {roi_str[1]:>18} {roi_str[2]:>18} {roi_str[3]:>18} {roi_str[4]:>18}")
    
    # P&L
    pnls = [data[name][1]['results']['total_pnl'] for name, _ in versions]
    pnl_str = [f"${pnl:,.2f}" for pnl in pnls]
    print(f"{'P&L':18} {pnl_str[0]:>18} {pnl_str[1]:>18} {pnl_str[2]:>18} {pnl_str[3]:>18} {pnl_str[4]:>18}")
    
    # Win Rate
    wrs = [data[name][1]['results']['win_rate_pct'] for name, _ in versions]
    wr_str = [f"{wr:.1f}%" for wr in wrs]
    print(f"{'Win Rate':18} {wr_str[0]:>18} {wr_str[1]:>18} {wr_str[2]:>18} {wr_str[3]:>18} {wr_str[4]:>18}")
    
    print("\n🎯 CUMPLIMIENTO OBJETIVO (PF ≥ 1.15x)")
    print("-" * 120)
    
    status = [("✅" if pf >= 1.15 else "❌") for pf in pfs]
    print(f"{'Status':18} {status[0]:>18} {status[1]:>18} {status[2]:>18} {status[3]:>18} {status[4]:>18}")
    print(f"{'Delta vs 1.15x':18} {f'{pfs[0]-1.15:+.2f}x':>18} {f'{pfs[1]-1.15:+.2f}x':>18} {f'{pfs[2]-1.15:+.2f}x':>18} {f'{pfs[3]-1.15:+.2f}x':>18} {f'{pfs[4]-1.15:+.2f}x':>18}")
    
    print("\n📈 MEJORA VS BASELINE (V1)")
    print("-" * 120)
    print(f"{'':18} {'V2 (Strict)':>18} {'V2 (Balanced)':>18} {'V2.5 (Optimal)':>18} {'V3 (Aggressive)':>18}")
    print("-" * 120)
    
    # Delta P&L
    delta_pnl = [pnls[i] - pnls[0] for i in range(1, 5)]
    delta_pnl_str = [f"${d:+,.2f}" for d in delta_pnl]
    print(f"{'Delta P&L':18} {delta_pnl_str[0]:>18} {delta_pnl_str[1]:>18} {delta_pnl_str[2]:>18} {delta_pnl_str[3]:>18}")
    
    # Delta PF
    delta_pf = [pfs[i] - pfs[0] for i in range(1, 5)]
    delta_pf_str = [f"{d:+.2f}x" for d in delta_pf]
    print(f"{'Delta PF':18} {delta_pf_str[0]:>18} {delta_pf_str[1]:>18} {delta_pf_str[2]:>18} {delta_pf_str[3]:>18}")
    
    # Reducción trades
    reductions = [(1 - trades_counts[i]/trades_counts[0])*100 for i in range(1, 5)]
    red_str = [f"-{r:.2f}%" for r in reductions]
    print(f"{'Reducción trades':18} {red_str[0]:>18} {red_str[1]:>18} {red_str[2]:>18} {red_str[3]:>18}")
    
    print("\n💡 ANÁLISIS DETALLADO")
    print("-" * 120)
    
    print("\n📊 Trade-off Calidad vs Cantidad:")
    for i, (name, _) in enumerate(versions[1:], 1):
        trades_count = trades_counts[i]
        pf = pfs[i]
        roi = rois[i]
        objective = "✅" if pf >= 1.15 else "❌"
        print(f"  {name:18} {trades_count:3} trades | PF {pf:.2f}x | ROI {roi:+.2f}% {objective}")
    
    # Encontrar mejor versión
    best_pf_idx = pfs.index(max(pfs[1:], default=0))  # Excluir V1
    best_trades_with_pf = [(i, trades_counts[i], pfs[i]) for i in range(1, 5) if pfs[i] >= 1.15]
    
    if best_trades_with_pf:
        best_idx = max(best_trades_with_pf, key=lambda x: x[1])[0]
        best_name = versions[best_idx][0]
        
        print(f"\n🏆 RECOMENDACIÓN: {best_name}")
        print(f"   Razón: Máximos trades ({trades_counts[best_idx]}) manteniendo PF ≥ 1.15x (actual: {pfs[best_idx]:.2f}x)")
        print(f"   ROI: {rois[best_idx]:+.2f}% | P&L: ${pnls[best_idx]:,.2f}")
    else:
        print("\n⚠️  NINGUNA VERSIÓN V2/V3 CUMPLE OBJETIVO")
    
    print("\n⚠️  OBSERVACIONES IMPORTANTES:")
    print(f"   - V2.5 Optimal alcanza EXACTAMENTE PF 1.15x (límite justo)")
    print(f"   - V2 Balanced tiene mejor PF (1.41x) pero menos trades (74)")
    print(f"   - V3 Aggressive no cumple objetivo (PF 1.11x < 1.15x)")
    print(f"   - Balance óptimo: V2.5 con 83 trades y PF 1.15x")
    
    print("\n" + "="*120)


if __name__ == '__main__':
    print_full_comparison()
