import pandas as pd
from datetime import datetime, timedelta

# Cargar forecast y filtrar solo señales recientes
df = pd.read_csv('reports/forecast/2025-11/forecast_with_patterns_tth.csv')
df['date'] = pd.to_datetime(df['date'])

# Obtener última fecha disponible
latest_date = df['date'].max()
print(f'📅 Última fecha en forecast: {latest_date.date()}')

# Filtrar solo señales de los últimos 5 días
cutoff = latest_date - timedelta(days=5)
recent = df[df['date'] >= cutoff].copy()

print(f'\n🔍 Señales de los últimos 5 días: {len(recent)}')
print(f'   - Con gate_ok=1: {len(recent[recent["gate_ok"]==1])}')

# Aplicar filtros del trade plan
filtered = recent[
    (recent['gate_ok'] == 1) &
    (recent['prob_win'] >= 0.56) &
    (recent['abs_y_hat'] >= 0.05) &
    (recent['etth_first_event'] <= 2.5) &
    (recent['p_tp_before_sl'] >= 0.65)
]

print(f'\n✅ Señales que pasan todos los filtros: {len(filtered)}')

if len(filtered) > 0:
    # Mostrar top 5
    top = filtered.nlargest(5, 'tth_score')[['date', 'ticker', 'entry_price', 'prob_win', 'etth_first_event', 'p_tp_before_sl', 'tth_score']]
    print('\n🎯 TOP 5 SEÑALES RECIENTES:')
    print(top.to_string(index=False))
    
    # Comparar con precios actuales
    prices = pd.read_csv('data/us/ohlcv_us_daily.csv')
    prices['date'] = pd.to_datetime(prices['date'])
    latest_prices = prices.groupby('ticker').tail(1)[['ticker', 'date', 'close']]
    
    print('\n📊 VALIDACIÓN CON PRECIOS ACTUALES:')
    for _, row in top.head(3).iterrows():
        ticker = row['ticker']
        entry = row['entry_price']
        current_price = latest_prices[latest_prices['ticker'] == ticker]['close'].values
        if len(current_price) > 0:
            current = current_price[0]
            diff_pct = ((current - entry) / entry) * 100
            print(f'{ticker:5s} | Plan: ${entry:.2f} | Actual: ${current:.2f} | Diff: {diff_pct:+.2f}%')
else:
    print('\n⚠️  No hay señales recientes que pasen los filtros.')
    print('    Necesitas relajar los umbrales o esperar más datos.')
