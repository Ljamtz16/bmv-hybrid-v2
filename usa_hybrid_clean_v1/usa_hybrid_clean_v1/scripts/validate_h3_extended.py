"""
Validación extendida del sistema H3 - Nov/Dic 2025
Implementa los criterios de aceptación y métricas adicionales solicitadas
"""
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime
from scipy import stats

def wilson_confidence_interval(wins, total, confidence=0.95):
    """Intervalo de confianza Wilson para proporción"""
    if total == 0:
        return 0, 0, 0
    
    p = wins / total
    z = stats.norm.ppf((1 + confidence) / 2)
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    adjustment = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    interval = adjustment / denominator
    
    return centre, centre - interval, centre + interval

def analyze_h3_month(month_str, base_path='reports/forecast'):
    """Análisis completo de un mes H3"""
    month_path = Path(base_path) / month_str
    
    if not month_path.exists():
        return None
    
    # Cargar datos
    trades = pd.read_csv(month_path / 'trades_detailed.csv')
    with open(month_path / 'kpi_all.json', 'r') as f:
        kpi = json.load(f)
    
    # 1. Métricas básicas
    n_trades = len(trades)
    tp_hits = (trades['close_reason'] == 'TP_HIT').sum()
    sl_hits = (trades['close_reason'] == 'SL_HIT').sum()
    exp_hits = (trades['close_reason'] == 'HORIZON_END').sum()
    
    p_win = tp_hits / n_trades if n_trades > 0 else 0
    
    # 2. Intervalo de confianza Wilson 95%
    p_center, p_lower, p_upper = wilson_confidence_interval(tp_hits, n_trades)
    
    # 3. Expectativa por trade
    avg_tp_pct = trades[trades['close_reason'] == 'TP_HIT']['tp_pct'].mean() if tp_hits > 0 else 0
    avg_sl_pct = abs(trades[trades['close_reason'] == 'SL_HIT']['sl_pct'].mean()) if sl_hits > 0 else 0
    
    ev_gross = p_win * avg_tp_pct - (1 - p_win) * avg_sl_pct
    
    # 4. Costos (asumiendo 50 bps roundtrip = 0.5%)
    cost_pct = 0.005
    ev_net = ev_gross - cost_pct
    
    # 5. ETTH y duración
    etth_median = trades['duration_days'].median()
    etth_mean = trades['duration_days'].mean()
    
    # 6. Drawdown (simulado desde PnL acumulado)
    trades_sorted = trades.sort_values('entry_dt')
    cumulative_pnl = trades_sorted['pnl'].cumsum()
    running_max = cumulative_pnl.cummax()
    drawdown = (cumulative_pnl - running_max) / 1100  # Capital inicial
    mdd = drawdown.min()
    
    # 7. Distribución de retornos por outcome
    distribution = trades.groupby('close_reason').agg({
        'pnl': ['count', 'sum', 'mean'],
        'duration_days': 'mean'
    }).round(2)
    distribution.columns = ['_'.join(col).strip() for col in distribution.columns]
    distribution = distribution.reset_index()
    
    # 8. Por ticker/sector
    ticker_stats = trades.groupby('ticker').agg({
        'pnl': 'sum',
        'close_reason': lambda x: (x == 'TP_HIT').mean()
    }).round(2)
    ticker_stats.columns = ['Total_PnL', 'Win_Rate']
    
    # 9. Curva de supervivencia (días hasta TP/SL)
    survival_curve = {}
    for day in range(1, int(trades['duration_days'].max()) + 1):
        n_active = (trades['duration_days'] >= day).sum()
        survival_curve[f'D{day}'] = n_active / n_trades if n_trades > 0 else 0
    
    # 10. Criterios de aceptación
    acceptance = {
        'p_win_min': bool(p_win >= 0.62),
        'ev_net_min': bool(ev_net >= 0.035),  # 3.5%
        'etth_median_max': bool(etth_median <= 4.0),
        'mdd_max': bool(mdd >= -0.06)  # MDD < 6%
    }
    
    report = {
        'month': month_str,
        'timestamp': datetime.now().isoformat(),
        'sample_size': n_trades,
        'outcomes': {
            'TP_HIT': int(tp_hits),
            'SL_HIT': int(sl_hits),
            'HORIZON_END': int(exp_hits)
        },
        'win_rate': {
            'point_estimate': round(p_win, 4),
            'wilson_95_ci': {
                'center': round(p_center, 4),
                'lower': round(p_lower, 4),
                'upper': round(p_upper, 4)
            }
        },
        'expectancy': {
            'avg_tp_pct': round(avg_tp_pct, 4),
            'avg_sl_pct': round(avg_sl_pct, 4),
            'ev_gross_pct': round(ev_gross, 4),
            'cost_pct': cost_pct,
            'ev_net_pct': round(ev_net, 4)
        },
        'duration': {
            'etth_median_days': round(etth_median, 2),
            'etth_mean_days': round(etth_mean, 2)
        },
        'risk': {
            'mdd_pct': round(mdd, 4),
            'total_pnl': round(trades['pnl'].sum(), 2),
            'return_pct': round((trades['pnl'].sum() / 1100) * 100, 2)
        },
        'acceptance_criteria': acceptance,
        'all_criteria_passed': all(acceptance.values()),
        'distribution': distribution.to_dict(),
        'ticker_breakdown': ticker_stats.to_dict(),
        'survival_curve': survival_curve
    }
    
    return report

def generate_walkforward_report(months=['2025-10', '2025-11', '2025-12']):
    """Walk-forward validation Nov/Dic"""
    results = []
    
    for month in months:
        print(f"\n{'='*60}")
        print(f"Analizando {month}...")
        print(f"{'='*60}")
        
        report = analyze_h3_month(month)
        if report:
            results.append(report)
            
            # Print summary
            print(f"\n✅ Muestra: {report['sample_size']} trades")
            print(f"📊 Win rate: {report['win_rate']['point_estimate']:.1%}")
            print(f"   Wilson 95% CI: [{report['win_rate']['wilson_95_ci']['lower']:.1%}, "
                  f"{report['win_rate']['wilson_95_ci']['upper']:.1%}]")
            print(f"💰 EV net: {report['expectancy']['ev_net_pct']:.2%} por trade")
            print(f"⏱️  ETTH mediana: {report['duration']['etth_median_days']:.1f} días")
            print(f"📉 MDD: {report['risk']['mdd_pct']:.2%}")
            print(f"🎯 Return: {report['risk']['return_pct']:.1f}%")
            
            print(f"\n🔍 Criterios de aceptación:")
            for criterion, passed in report['acceptance_criteria'].items():
                status = '✅' if passed else '❌'
                print(f"   {status} {criterion}: {passed}")
            
            print(f"\n{'✅' if report['all_criteria_passed'] else '⚠️'} "
                  f"Estado: {'APROBADO' if report['all_criteria_passed'] else 'REVISAR'}")
        else:
            print(f"⚠️  No se encontraron datos para {month}")
    
    # Guardar reporte consolidado
    output_path = Path('reports/H3_WALKFORWARD_VALIDATION.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"📄 Reporte guardado: {output_path}")
    print(f"{'='*60}")
    
    return results

if __name__ == '__main__':
    # Ejecutar walk-forward Oct/Nov/Dic
    results = generate_walkforward_report(['2025-10', '2025-11', '2025-12'])
    
    # Resumen multi-mes
    if len(results) > 1:
        print(f"\n\n{'='*60}")
        print("📊 RESUMEN MULTI-MES")
        print(f"{'='*60}")
        
        total_trades = sum(r['sample_size'] for r in results)
        total_tp = sum(r['outcomes']['TP_HIT'] for r in results)
        total_pnl = sum(r['risk']['total_pnl'] for r in results)
        
        print(f"\nTrades totales: {total_trades}")
        print(f"Win rate agregado: {total_tp/total_trades:.1%}")
        print(f"PnL total: ${total_pnl:.2f}")
        print(f"Return acumulado: {(total_pnl/1100)*100:.1f}%")
        
        # Intervalo de confianza agregado
        p_c, p_l, p_u = wilson_confidence_interval(total_tp, total_trades)
        print(f"Wilson 95% CI: [{p_l:.1%}, {p_u:.1%}]")
        
        # Meses aprobados
        approved = sum(1 for r in results if r['all_criteria_passed'])
        print(f"\nMeses aprobados: {approved}/{len(results)}")
