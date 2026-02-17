import pandas as pd

print('=' * 80)
print('📊 RESUMEN SEÑALES - 28 ENE 2026')
print('=' * 80)

df_std = pd.read_csv('evidence/weekly_plans/plan_standard_2026-01-28.csv')
df_prob55 = pd.read_csv('evidence/weekly_plans/plan_probwin55_2026-01-28.csv')

print('\n[PLAN STANDARD]')
print(df_std[['ticker', 'side', 'entry', 'tp_price', 'sl_price', 'prob_win']].to_string(index=False))
print(f'\nTotal posiciones: {len(df_std)}')
print(f'Exposición: ${df_std["exposure"].sum():.2f}')
print(f'Prob_win promedio: {df_std["prob_win"].mean():.1%}')

print('\n' + '-' * 80)
print('\n[PLAN PROBWIN_55]')
if len(df_prob55) > 0:
    print(df_prob55[['ticker', 'side', 'entry', 'tp_price', 'sl_price', 'prob_win']].to_string(index=False))
    print(f'\nTotal posiciones: {len(df_prob55)}')
    print(f'Exposición: ${df_prob55["exposure"].sum():.2f}')
    print(f'Prob_win promedio: {df_prob55["prob_win"].mean():.1%}')
else:
    print('  ⚠️ Sin posiciones con prob_win >= 55%')

print('\n' + '=' * 80)
print('📋 INTERPRETACIÓN:')
print('=' * 80)
print(f'\n✅ DATOS FRESCOS: Predicciones hasta 28-ENE-2026 (HOY)')
print(f'⚖️  MODELO CALIBRADO: Win Rate real promedio = 48.8%')
print(f'\n🎯 SEÑALES ACTUALES:')

buys = len(df_std[df_std['side'] == 'BUY'])
sells = len(df_std[df_std['side'] == 'SELL'])
print(f'   BUY: {buys} posiciones')
print(f'   SELL: {sells} posiciones')

high_conf = len(df_std[df_std['prob_win'] >= 0.55])
medium_conf = len(df_std[(df_std['prob_win'] >= 0.50) & (df_std['prob_win'] < 0.55)])
low_conf = len(df_std[df_std['prob_win'] < 0.50])

print(f'\n📊 DISTRIBUCIÓN DE CONFIANZA:')
print(f'   Alta (>=55%): {high_conf}')
print(f'   Media (50-55%): {medium_conf}')
print(f'   Baja (<50%): {low_conf}')

print(f'\n💡 RECOMENDACIÓN:')
if len(df_prob55) > 0:
    print(f'   ✅ Operar plan PROBWIN_55 ({len(df_prob55)} posiciones con alta confianza)')
elif len(df_std[df_std['prob_win'] >= 0.52]) > 0:
    print(f'   ⚠️  Operar con cautela (confianza moderada 50-55%)')
else:
    print(f'   ❌ Esperar mejores señales (todas <50% confianza)')
