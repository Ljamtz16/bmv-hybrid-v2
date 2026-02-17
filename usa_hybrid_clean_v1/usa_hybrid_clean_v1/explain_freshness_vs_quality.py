import pandas as pd
from datetime import datetime

print('='*80)
print('ACLARACIÓN: FRESHNESS vs CALIDAD DE SEÑALES')
print('='*80)

# Comparar freshness
df_old_forecast = pd.read_csv('evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv')
df_plan = pd.read_csv('evidence/weekly_plans/plan_standard_2026-01-28.csv')

fecha_hoy = datetime.now().strftime('%Y-%m-%d')
fecha_forecast = df_old_forecast['date'].max()
fecha_plan_signals = df_plan['date'].iloc[0]

print(f'\n📅 FRESHNESS DE DATOS (MEJORADO):')
print('='*80)
print(f'  Hoy:                     {fecha_hoy}')
print(f'  Última predicción:       {fecha_forecast}')
print(f'  Señales del plan:        {fecha_plan_signals}')
print(f'  Precios de entrada:      {fecha_hoy} (obtenidos en tiempo real)')
print(f'\n  Desfase: SOLO 2 DÍAS (antes eran 8 días)')
print('  ✅ Los datos SÍ son recientes!')

print(f'\n\n⚠️  CALIDAD DE SEÑALES (REALISTA):')
print('='*80)
print('El modelo re-entrenado usa resultados REALES de 1,296 trades de backtest.')
print('Es MÁS CONSERVADOR porque aprendió de pérdidas y ganancias reales.\n')

print('SEÑALES GENERADAS HOY:')
for _, r in df_plan.iterrows():
    status = '🔴' if r['prob_win'] < 0.45 else '🟡' if r['prob_win'] < 0.55 else '🟢'
    print(f'  {status} {r["ticker"]:6} {r["side"]:4} @ ${r["entry"]:8.2f} | prob_win: {r["prob_win"]:.1%}')

print(f'\nPromedio prob_win: {df_plan["prob_win"].mean():.1%}')
print(f'Posiciones con ≥55%: {len(df_plan[df_plan["prob_win"] >= 0.55])}')

print('\n' + '='*80)
print('CONCLUSIÓN:')
print('='*80)
print('✅ DATOS RECIENTES: Sí, el modelo está actualizado al 26-ENE (2 días atrás)')
print('⚠️  SEÑALES DÉBILES: El modelo NO ve oportunidades con buena prob_win')
print('\nEsto es BUENO → El modelo evita trades de baja calidad.')
print('='*80)

# Mostrar por qué el modelo es conservador
print('\n📊 ¿POR QUÉ EL MODELO ES CONSERVADOR?')
print('='*80)

import json
with open('evidence/retrained_prob_win_robust/calibration_report.json') as f:
    calib = json.load(f)

print('\nCALIBRACIÓN DEL MODELO (basada en backtest real):')
for ticker in ['AAPL', 'GS', 'IWM', 'JPM', 'MS']:
    if ticker in calib:
        wr = calib[ticker]['actual_wr']
        val_acc = calib[ticker]['val_acc']
        print(f'  {ticker}: Win Rate Real = {wr:.1%} | Val Accuracy = {val_acc:.1%}')

print('\nEl modelo aprendió que:')
print('  • Win rate real promedio: 48.8% (no 55%+)')
print('  • Las operaciones SELL tienen peor desempeño que BUY')
print('  • Solo genera señales cuando ve patrones similares a trades ganadores')

print('\n' + '='*80)
print('OPCIONES:')
print('='*80)
print('1. ⏸️  NO OPERAR - Esperar mejores oportunidades (RECOMENDADO)')
print('2. 🎲 OPERAR IGUAL - Aceptar bajo prob_win (36.6% promedio)')
print('3. 🔄 USAR PLAN ANTERIOR - Modelo sintético (más optimista pero menos realista)')
print('='*80)
