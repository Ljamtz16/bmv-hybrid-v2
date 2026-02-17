import pandas as pd
from datetime import datetime

print('='*80)
print('¿POR QUÉ LAS PREDICCIONES SON DEL 26-ENE?')
print('='*80)

# Verificar datos disponibles
print('\n📊 DATOS DISPONIBLES EN EL SISTEMA:')
print('='*80)

intraday_file = r"C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\data\us\intraday_15m\consolidated_15m.parquet"
df_intraday = pd.read_parquet(intraday_file)
df_intraday['date'] = pd.to_datetime(df_intraday['timestamp']).dt.tz_localize(None).dt.date

print(f'\nArchivo: consolidated_15m.parquet')
print(f'  Total barras: {len(df_intraday):,}')
print(f'  Rango de fechas: {df_intraday["date"].min()} → {df_intraday["date"].max()}')
print(f'  Última fecha disponible: {df_intraday["date"].max()}')

# Contar barras por ticker en últimas fechas
print(f'\n📅 ÚLTIMAS 5 FECHAS DISPONIBLES:')
print('='*80)
last_dates = sorted(df_intraday['date'].unique())[-5:]
for date in last_dates:
    count = len(df_intraday[df_intraday['date'] == date])
    tickers = df_intraday[df_intraday['date'] == date]['ticker'].nunique()
    print(f'  {date}: {count} barras | {tickers} tickers')

# Verificar forecast generado
print(f'\n🔮 FORECAST GENERADO:')
print('='*80)
df_forecast = pd.read_csv('evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv')
print(f'  Rango: {df_forecast["date"].min()} → {df_forecast["date"].max()}')
print(f'  Última predicción: {df_forecast["date"].max()}')

# Explicación
print('\n' + '='*80)
print('EXPLICACIÓN:')
print('='*80)
print('\n¿Por qué no hay predicciones para el 27 o 28-ENE?')
print('-'*80)
print('Para generar predicciones, el modelo necesita:')
print('  1. Datos intraday agregados a diario')
print('  2. Features calculados (volatilidad, momentum, ATR, etc.)')
print('  3. Estos features se calculan desde datos históricos')
print()
print(f'El último día con datos completos es: {df_intraday["date"].max()}')
print(f'Por lo tanto, las predicciones más recientes son: {df_forecast["date"].max()}')
print()
print('Para tener predicciones del 27 o 28-ENE, necesitas:')
print('  ✅ Descargar/actualizar datos intraday hasta hoy')
print('  ✅ Re-ejecutar el proceso de agregación diaria')
print('  ✅ Re-generar forecast con los datos actualizados')

# Verificar si es fin de semana
fecha_hoy = datetime.now()
dia_semana = fecha_hoy.strftime('%A')
print(f'\n📅 HOY ES: {fecha_hoy.strftime("%Y-%m-%d")} ({dia_semana})')

if fecha_hoy.weekday() >= 5:
    print('⚠️  Es fin de semana - el mercado está CERRADO')
    print('   No hay datos nuevos porque no hubo trading')
else:
    print('✅ Es día de semana - el mercado debería estar abierto')
    print('   Los datos intraday necesitan actualizarse')

print('\n' + '='*80)
print('SOLUCIÓN:')
print('='*80)
print('Para tener predicciones actualizadas al 28-ENE:')
print()
print('1. Actualizar datos intraday (descargar 27 y 28-ENE)')
print('2. Re-entrenar modelo: python retrain_prob_win_from_backtest.py')
print('3. Re-generar forecast: python generate_forecast_retrained.py')
print('4. Re-generar planes: python generate_weekly_plans.py')
print()
print('NOTA: Si el mercado está cerrado (fin de semana), no hay datos nuevos.')
print('      Las predicciones del 26-ENE son las más recientes posibles.')
print('='*80)
