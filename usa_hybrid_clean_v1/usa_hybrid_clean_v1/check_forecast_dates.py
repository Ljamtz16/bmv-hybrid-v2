import pandas as pd

# Verificar forecast
df = pd.read_csv('reports/forecast/2025-11/forecast_with_patterns_tth.csv')
df['date'] = pd.to_datetime(df['date'])

print('='*60)
print('ANÁLISIS DEL FORECAST')
print('='*60)
print(f'Rango de fechas: {df["date"].min()} a {df["date"].max()}')
print(f'Total filas: {len(df)}')
print(f'Fechas únicas: {df["date"].nunique()}')

latest = df['date'].max()
latest_df = df[df['date'] == latest]
print(f'\n📅 Señales para la fecha más reciente ({latest.date()}): {len(latest_df)}')

# Verificar si hay señales recientes con gate_ok
if 'gate_ok' in df.columns:
    latest_ok = latest_df[latest_df['gate_ok'] == 1]
    print(f'   - Con gate_ok=1: {len(latest_ok)}')
    if len(latest_ok) > 0:
        print(f'\n🎯 Tickers con señales válidas hoy:')
        print(latest_ok['ticker'].unique())
