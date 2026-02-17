import pandas as pd

print('='*70)
print('ANÁLISIS DEL PLAN ACTUALIZADO (Modelo re-entrenado)')
print('='*70)

df = pd.read_csv('evidence/weekly_plans/plan_standard_2026-01-28.csv')

print(f'\n📅 Generado: {df["generated_at"].iloc[0]}')
print(f'📊 Predicciones basadas en: {df["date"].iloc[0]}')

print(f'\n💼 POSICIONES GENERADAS:')
print('='*70)
for _, r in df.iterrows():
    print(f'{r["ticker"]:6} {r["side"]:4} @ ${r["entry"]:8.2f} | '
          f'TP: ${r["tp_price"]:8.2f} | SL: ${r["sl_price"]:8.2f} | '
          f'prob_win: {r["prob_win"]:.2%}')

print(f'\n📈 RESUMEN:')
print('='*70)
print(f'Total posiciones: {len(df)}')
print(f'Exposición total: ${df["exposure"].sum():.2f}')
print(f'\nDistribución:')
print(f'  BUY:  {len(df[df["side"]=="BUY"])}')
print(f'  SELL: {len(df[df["side"]=="SELL"])}')
print(f'\nPromedio prob_win: {df["prob_win"].mean():.1%}')

# Análisis de calidad
print(f'\n⚠️  ANÁLISIS DE SEÑALES:')
print('='*70)
high_conf = len(df[df["prob_win"] >= 0.55])
med_conf = len(df[(df["prob_win"] >= 0.50) & (df["prob_win"] < 0.55)])
low_conf = len(df[df["prob_win"] < 0.50])

print(f'Alta confianza (≥55%):    {high_conf} posiciones')
print(f'Media confianza (50-55%): {med_conf} posiciones')
print(f'Baja confianza (<50%):    {low_conf} posiciones')

if high_conf == 0:
    print('\n🔴 ADVERTENCIA: No hay señales con alta confianza (≥55%)')
    print('   Recomendación: NO OPERAR hoy o esperar mejores señales')
else:
    print(f'\n🟢 {high_conf} señales con confianza adecuada')

print('\n' + '='*70)
print('DIFERENCIAS vs PLAN ANTERIOR:')
print('='*70)
print('ANTES (predicciones del 20-ENE):')
print('  4 posiciones: AAPL BUY, GS SELL, MS SELL, IWM SELL')
print('  1 con prob_win ≥55% (AAPL)')
print('\nAHORA (predicciones actualizadas al 26-ENE):')
print('  2 posiciones: AAPL SELL, IWM SELL')
print('  0 con prob_win ≥55%')
print('\n⚠️  El modelo re-entrenado es MÁS CONSERVADOR')
print('   Solo genera señales cuando tiene confianza real basada en')
print('   resultados históricos de backtest (no predicciones sintéticas)')
print('='*70)
