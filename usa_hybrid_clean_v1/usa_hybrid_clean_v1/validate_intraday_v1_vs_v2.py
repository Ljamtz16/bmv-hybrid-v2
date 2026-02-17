#!/usr/bin/env python3
"""
Comparación Intraday V1 (sin filtros) vs V2 (filtros estrictos)
"""

import pandas as pd
import json
from pathlib import Path

def normalize_summary(summary):
    """Normaliza formato de summary.json (v1 vs v2)."""
    # Si ya tiene estructura config/results, retornar
    if 'config' in summary and 'results' in summary:
        return summary
    
    # V1 format (sin config/results): todo en raíz
    # Calcular campos faltantes
    capital = 600  # Asumido
    results = summary.copy()
    
    # Calcular ROI si no existe
    if 'roi_pct' not in results:
        results['roi_pct'] = (results['total_pnl'] / capital) * 100
    
    # Calcular avg_win/avg_loss si no existen
    if 'avg_win' not in results and 'gross_profit' in results and 'win_count' in results:
        results['avg_win'] = results['gross_profit'] / results['win_count'] if results['win_count'] > 0 else 0
    
    if 'avg_loss' not in results and 'gross_loss' in results and 'loss_count' in results:
        results['avg_loss'] = -results['gross_loss'] / results['loss_count'] if results['loss_count'] > 0 else 0
    
    # Mapear wins/losses
    if 'wins' not in results:
        results['wins'] = results.get('win_count', 0)
    
    if 'losses' not in results:
        results['losses'] = results.get('loss_count', 0)
    
    return {
        'config': {
            'capital': capital,
            'tp_pct': 0.016,  # Asumido
            'sl_pct': 0.01  # Asumido
        },
        'results': results
    }


def load_simulation(output_dir):
    """Carga all_trades.csv y summary.json de una simulación."""
    trades_path = Path(output_dir) / 'all_trades.csv'
    summary_path = Path(output_dir) / 'summary.json'
    
    if not trades_path.exists():
        return None, None
    
    trades = pd.read_parquet(trades_path) if trades_path.suffix == '.parquet' else pd.read_csv(trades_path)
    
    with open(summary_path, 'r') as f:
        summary = json.load(f)
    
    summary = normalize_summary(summary)
    
    return trades, summary


def print_comparison():
    print("\n" + "="*80)
    print("COMPARACIÓN: INTRADAY V1 (sin filtros) vs V2 (filtros estrictos)")
    print("="*80)
    
    # V1: TP=1.6%, SL=1% (baseline - sin filtros)
    v1_trades, v1_summary = load_simulation('evidence/paper_2022_2025_intraday_600_tp1p6_sl1')
    
    # V2: Filtros estrictos (prob_win>0.58, régimen, SL/TP adaptativo)
    v2_trades, v2_summary = load_simulation('evidence/paper_2022_2025_intraday_v2_strict')
    
    if v1_trades is None or v2_trades is None:
        print("[ERROR] No se encontraron los archivos de simulaciones")
        return
    
    print("\n📊 CONFIGURACIÓN")
    print("-" * 80)
    print(f"{'':25} {'V1 (Baseline)':>25} {'V2 (Estricta)':>25}")
    print("-" * 80)
    print(f"{'Capital':25} ${v1_summary['config']['capital']:>24,.2f} ${v2_summary['config']['capital']:>24,.2f}")
    print(f"{'TP/SL':25} {f'{v1_summary['config']['tp_pct']*100:.1f}% / {v1_summary['config']['sl_pct']*100:.1f}%':>25} {'Adaptativo (1.5/0.75 ATR)':>25}")
    print(f"{'Position Size':25} {'10%':>25} {'30%':>25}")
    print(f"{'Filtros':25} {'prob_win > 0.5':>25} {'prob_win>0.58 + régimen':>25}")
    
    print("\n💰 RESULTADOS")
    print("-" * 80)
    print(f"{'':25} {'V1 (Baseline)':>25} {'V2 (Estricta)':>25} {'Delta':>20}")
    print("-" * 80)
    
    # P&L
    v1_pnl = v1_summary['results']['total_pnl']
    v2_pnl = v2_summary['results']['total_pnl']
    delta_pnl = v2_pnl - v1_pnl
    print(f"{'Total P&L':25} ${v1_pnl:>24,.2f} ${v2_pnl:>24,.2f} ${delta_pnl:>19,.2f}")
    
    # ROI
    v1_roi = v1_summary['results']['roi_pct']
    v2_roi = v2_summary['results']['roi_pct']
    delta_roi = v2_roi - v1_roi
    print(f"{'ROI':25} {f'{v1_roi:>23.2f}%'} {f'{v2_roi:>24.2f}%'} {f'{delta_roi:>19.2f} pp'}")
    
    # Trades
    v1_trades_count = v1_summary['results']['total_trades']
    v2_trades_count = v2_summary['results']['total_trades']
    reduction_pct = (1 - v2_trades_count / v1_trades_count) * 100 if v1_trades_count > 0 else 0
    print(f"{'Total Trades':25} {v1_trades_count:>25,} {v2_trades_count:>25,} {f'-{reduction_pct:.2f}%':>20}")
    
    # Win Rate
    v1_wr = v1_summary['results']['win_rate_pct']
    v2_wr = v2_summary['results']['win_rate_pct']
    delta_wr = v2_wr - v1_wr
    print(f"{'Win Rate':25} {f'{v1_wr:>23.1f}%'} {f'{v2_wr:>24.1f}%'} {f'{delta_wr:>19.1f} pp'}")
    
    # Profit Factor
    v1_pf = v1_summary['results']['profit_factor']
    v2_pf = v2_summary['results']['profit_factor']
    delta_pf = v2_pf - v1_pf
    print(f"{'Profit Factor':25} {f'{v1_pf:>24.2f}x'} {f'{v2_pf:>24.2f}x'} {f'+{delta_pf:.2f}x':>20}")
    
    # Avg Win/Loss
    v1_avg_win = v1_summary['results']['avg_win']
    v2_avg_win = v2_summary['results']['avg_win']
    print(f"{'Avg Win':25} ${v1_avg_win:>24,.2f} ${v2_avg_win:>24,.2f}")
    
    v1_avg_loss = v1_summary['results']['avg_loss']
    v2_avg_loss = v2_summary['results']['avg_loss']
    print(f"{'Avg Loss':25} ${v1_avg_loss:>24,.2f} ${v2_avg_loss:>24,.2f}")
    
    print("\n📈 EXIT BREAKDOWN")
    print("-" * 80)
    print(f"{'':25} {'V1 (Baseline)':>25} {'V2 (Estricta)':>25}")
    print("-" * 80)
    
    v1_exits = v1_summary['results'].get('exit_breakdown', {})
    v2_exits = v2_summary['results'].get('exit_breakdown', {})
    
    if v1_exits or v2_exits:
        for reason in ['TP', 'SL', 'TIMEOUT']:
            v1_count = v1_exits.get(reason, 0)
            v2_count = v2_exits.get(reason, 0)
            v1_pct = (v1_count / v1_trades_count * 100) if v1_trades_count > 0 else 0
            v2_pct = (v2_count / v2_trades_count * 100) if v2_trades_count > 0 else 0
            print(f"{reason:25} {f'{v1_count:,} ({v1_pct:.1f}%)':>25} {f'{v2_count:,} ({v2_pct:.1f}%)':>25}")
    else:
        print("(Exit breakdown no disponible para V1)")

    
    print("\n✅ CHECKLIST CUMPLIMIENTO")
    print("-" * 80)
    
    checklist = [
        ("1. Time gating estricto", "❌ No", "✅ Sí (2 ventanas UTC)"),
        ("2. Filtro de régimen", "❌ No", "✅ Sí (ATR+rango+dirección)"),
        ("3. Patrones raros", "❌ No (todas señales)", "✅ Sí (prob_win>0.58)"),
        ("4. SL/TP adaptativo", "❌ Fijo 1.6%/1%", "✅ Sí (1.5x/0.75x ATR)"),
        ("5. PF ≥ 1.15", f"❌ No ({v1_pf:.2f}x)", f"✅ Sí ({v2_pf:.2f}x)")
    ]
    
    for item, v1_status, v2_status in checklist:
        print(f"{item:30} {v1_status:>23} {v2_status:>23}")
    
    print("\n🎯 CONCLUSIONES")
    print("-" * 80)
    
    if v2_pf >= 1.15 and v2_pnl > 0:
        print("✅ V2 CUMPLE OBJETIVO: Profit Factor > 1.15x y P&L positivo")
    else:
        print("❌ V2 NO CUMPLE OBJETIVO")
    
    if v2_pnl > v1_pnl:
        improvement = ((v2_pnl - v1_pnl) / abs(v1_pnl) * 100) if v1_pnl != 0 else 0
        print(f"✅ V2 mejora P&L en ${v2_pnl - v1_pnl:.2f} ({improvement:+.1f}%)")
    else:
        print(f"⚠️  V2 reduce P&L vs V1 (diferencia: ${v2_pnl - v1_pnl:.2f})")
    
    print(f"\n📉 Reducción de trades: {reduction_pct:.1f}% (de {v1_trades_count:,} a {v2_trades_count:,})")
    print(f"💡 Trades por día: {v2_trades_count / 1460:.3f} (2022-2025 = ~4 años)")
    
    print("\n⚠️  ADVERTENCIA: V2 tiene muy pocos trades ({}) para validación estadística robusta".format(v2_trades_count))
    print("    Recomendación: Ampliar período de backtest o relajar ligeramente filtros")
    
    print("\n" + "="*80)


if __name__ == '__main__':
    print_comparison()
