"""
Recopila resultados del pipeline intraday para octubre 2025
"""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import json

def collect_october_plans():
    """Recopilar todos los planes de octubre."""
    results = []
    
    # Fechas de octubre (días hábiles)
    start = datetime(2025, 10, 13)
    end = datetime(2025, 10, 31)
    
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        
        # Saltar fines de semana
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        # Buscar plan
        plan_file = Path(f"reports/intraday/{date_str}/trade_plan_intraday.csv")
        stats_file = Path(f"reports/intraday/{date_str}/plan_stats.json")
        
        if stats_file.exists():
            with open(stats_file) as f:
                stats = json.load(f)
            
            # Cargar plan para detalles
            plan_detail = None
            if plan_file.exists():
                plan_df = pd.read_csv(plan_file)
                if len(plan_df) > 0:
                    plan_detail = plan_df.to_dict('records')
            
            results.append({
                'date': date_str,
                'n_signals': stats.get('n_signals_initial', 0),
                'n_filtered': stats.get('n_signals_filtered', 0),
                'n_plan': stats.get('n_plan', 0),
                'exposure': stats.get('total_exposure', 0),
                'avg_prob': stats.get('avg_prob_win', 0),
                'avg_etth': stats.get('avg_etth', 0),
                'trades': plan_detail
            })
        else:
            results.append({
                'date': date_str,
                'n_signals': 0,
                'n_filtered': 0,
                'n_plan': 0,
                'exposure': 0,
                'avg_prob': 0,
                'avg_etth': 0,
                'trades': None
            })
        
        current += timedelta(days=1)
    
    return pd.DataFrame(results)


def print_summary(df):
    """Imprimir resumen."""
    print("\n" + "="*80)
    print("RESUMEN OCTUBRE 2025 - Pipeline Intraday")
    print("="*80)
    
    total_days = len(df)
    days_with_signals = (df['n_signals'] > 0).sum()
    days_with_plan = (df['n_plan'] > 0).sum()
    total_trades = df['n_plan'].sum()
    total_exposure = df['exposure'].sum()
    
    print(f"\nDías analizados: {total_days}")
    print(f"Días con señales: {days_with_signals} ({days_with_signals/total_days*100:.1f}%)")
    print(f"Días con plan: {days_with_plan} ({days_with_plan/total_days*100:.1f}%)")
    print(f"Total trades: {total_trades}")
    print(f"Trades/día (promedio): {total_trades/total_days:.2f}")
    print(f"Exposure total: ${total_exposure:.2f}")
    print(f"Exposure promedio: ${total_exposure/max(days_with_plan, 1):.2f}")
    
    # Detalles por día
    print(f"\n{'='*80}")
    print(f"{'Fecha':<12} {'Señales':<10} {'Filtradas':<10} {'Plan':<6} {'Exposure':<12} {'Prob':<8} {'ETTH':<8}")
    print(f"{'='*80}")
    
    for _, row in df.iterrows():
        if row['n_plan'] > 0:
            print(f"{row['date']:<12} {row['n_signals']:<10} {row['n_filtered']:<10} "
                  f"{row['n_plan']:<6} ${row['exposure']:<11.2f} {row['avg_prob']:<7.1%} {row['avg_etth']:<7.2f}d")
    
    # Trades detail
    print(f"\n{'='*80}")
    print("DETALLE DE TRADES")
    print(f"{'='*80}")
    
    for _, row in df.iterrows():
        if row['trades'] and len(row['trades']) > 0:
            print(f"\n{row['date']}:")
            for trade in row['trades']:
                direction = trade.get('direction', 'LONG')
                ticker = trade.get('ticker', '?')
                entry = trade.get('entry_price', 0)
                qty = trade.get('qty', 0)
                exp = trade.get('exposure', 0)
                prob = trade.get('prob_win', 0)
                etth = trade.get('ETTH', 0)
                print(f"  {direction:<5} {ticker:<6} @ ${entry:>7.2f} | qty={qty:>5.2f} | exp=${exp:>7.2f} | prob={prob:.1%} | ETTH={etth:.2f}d")


if __name__ == "__main__":
    df = collect_october_plans()
    print_summary(df)
    
    # Guardar CSV
    out_file = "reports/intraday/october_2025_summary.csv"
    df_export = df.drop('trades', axis=1)
    df_export.to_csv(out_file, index=False)
    print(f"\n✅ Resumen guardado: {out_file}")
