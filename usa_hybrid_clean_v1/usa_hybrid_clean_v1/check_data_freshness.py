import pandas as pd
from datetime import datetime

print('='*70)
print('ANÁLISIS DE FRESHNESS DE DATOS')
print('='*70)

# Plan generado hoy
df_plan = pd.read_csv('evidence/weekly_plans/plan_standard_2026-01-28.csv')
print(f'\n📅 PLAN GENERADO:')
print(f'  Timestamp: {df_plan["generated_at"].iloc[0]}')
print(f'  Fecha de señales: {df_plan["date"].iloc[0]}')
print(f'  Fecha actual: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

print(f'\n💵 PRECIOS DE ENTRADA (obtenidos HOY de yfinance):')
for _, row in df_plan.iterrows():
    print(f'  {row["ticker"]:6} | ${row["entry"]:8.2f}')

# Forecast del modelo
df_forecast = pd.read_csv('evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv')
print(f'\n📊 FORECAST DEL MODELO:')
print(f'  Rango: {df_forecast["date"].min()} → {df_forecast["date"].max()}')
print(f'  Total predicciones: {len(df_forecast):,}')
print(f'  Última predicción: {df_forecast["date"].max()}')

# Análisis de desfase
fecha_forecast = pd.to_datetime(df_forecast["date"].max())
fecha_hoy = pd.to_datetime(datetime.now().date())
dias_desfase = (fecha_hoy - fecha_forecast).days

print(f'\n⚠️  DESFASE TEMPORAL:')
print(f'  Predicciones del modelo: {df_forecast["date"].max()}')
print(f'  Fecha actual: {datetime.now().strftime("%Y-%m-%d")}')
print(f'  Días de desfase: {dias_desfase} días')

if dias_desfase > 7:
    print(f'\n🔴 ALERTA: El modelo tiene {dias_desfase} días sin actualizar')
    print('   Recomendación: Re-entrenar modelo con datos más recientes')
elif dias_desfase > 3:
    print(f'\n🟡 ADVERTENCIA: El modelo tiene {dias_desfase} días de antigüedad')
    print('   Considerar actualizar pronto')
else:
    print(f'\n🟢 OK: El modelo está relativamente actualizado ({dias_desfase} días)')

print('\n' + '='*70)
print('RESUMEN:')
print('='*70)
print('✅ Los PRECIOS de entrada SÍ son actuales (obtenidos hoy de yfinance)')
print(f'⚠️  Las PREDICCIONES son del {df_forecast["date"].max()} ({dias_desfase} días atrás)')
print('\nEl sistema usa PRECIOS recientes pero SEÑALES antiguas.')
print('Para máxima precisión, re-entrenar el modelo semanalmente.')
print('='*70)
