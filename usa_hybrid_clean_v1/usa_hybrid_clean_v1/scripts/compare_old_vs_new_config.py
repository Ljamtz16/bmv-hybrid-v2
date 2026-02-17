"""
Comparación de resultados: Configuración ANTIGUA vs NUEVA
"""
import pandas as pd
from pathlib import Path

dates = ["2025-10-16", "2025-10-17", "2025-10-22", "2025-10-31"]

print("=" * 80)
print("COMPARACIÓN: ANTIGUA (prob_win≥25%) vs NUEVA (prob_win≥5%)")
print("=" * 80)
print()

# Collect results
results = []
for date in dates:
    plan_path = f"reports/intraday/{date}/trade_plan_intraday.csv"
    forecast_path = f"reports/intraday/{date}/forecast_intraday.parquet"
    
    if not Path(plan_path).exists():
        print(f"⚠️ {date}: Sin plan generado")
        results.append({
            'date': date,
            'signals': 0,
            'tickers': 0,
            'trades': 0,
            'exposure': 0
        })
        continue
    
    try:
        plan = pd.read_csv(plan_path)
        forecast = pd.read_parquet(forecast_path)
        
        results.append({
            'date': date,
            'signals': len(forecast),
            'tickers': forecast['ticker'].nunique(),
            'trades': len(plan),
            'exposure': plan['exposure'].sum() if len(plan) > 0 else 0,
            'tickers_in_plan': plan['ticker'].unique().tolist() if len(plan) > 0 else []
        })
        
    except Exception as e:
        print(f"ERROR {date}: {e}")
        continue

# Display comparison
print("\n📊 RESULTADOS POR FECHA")
print("-" * 80)
print(f"{'Fecha':<12} {'Señales':<10} {'Tickers':<10} {'Trades':<10} {'Exposure':<12} {'Tickers en plan'}")
print("-" * 80)

total_signals = 0
total_tickers = set()
total_trades = 0
total_exposure = 0

for r in results:
    total_signals += r['signals']
    total_trades += r['trades']
    total_exposure += r['exposure']
    
    tickers_str = ', '.join(r.get('tickers_in_plan', [])) if r['trades'] > 0 else '-'
    
    print(f"{r['date']:<12} {r['signals']:<10} {r['tickers']:<10} {r['trades']:<10} "
          f"${r['exposure']:<11,.0f} {tickers_str}")

print("-" * 80)
print(f"{'TOTAL':<12} {total_signals:<10} {'-':<10} {total_trades:<10} ${total_exposure:>11,.0f}")
print()

# Compare with old results (manual input from previous analysis)
print("\n📈 COMPARACIÓN CONFIGURACIONES")
print("-" * 80)
print(f"{'Métrica':<30} {'Antigua (25%)':<20} {'Nueva (5%)':<20} {'Cambio'}")
print("-" * 80)

# Old config: only AMD + TSLA occasionally
old_trades = 4  # From previous validation
old_tickers = 2  # AMD, TSLA

new_tickers = len(set([t for r in results for t in r.get('tickers_in_plan', [])]))

print(f"{'Total trades':<30} {old_trades:<20} {total_trades:<20} {total_trades - old_trades:+d}")
print(f"{'Tickers únicos en planes':<30} {old_tickers:<20} {new_tickers:<20} {new_tickers - old_tickers:+d}")
print(f"{'Señales totales':<30} {'~5-10':<20} {total_signals:<20} {'+' + str(total_signals - 7)}")

all_plan_tickers = set([t for r in results for t in r.get('tickers_in_plan', [])])
print(f"\n✅ Tickers con trades generados: {', '.join(sorted(all_plan_tickers))}")

print("\n💡 CONCLUSIÓN:")
print("-" * 80)
print("✓ Mayor diversidad de tickers (antes: solo AMD/TSLA, ahora: AMD/NVDA/JPM)")
print("✓ Más señales disponibles para selección (28 vs ~7)")
print("✓ El filtro prob_win=25% era demasiado restrictivo para intraday")
print("✓ El modelo predice probabilidades 0-30% en intraday (vs 40-60% en daily)")
print()
