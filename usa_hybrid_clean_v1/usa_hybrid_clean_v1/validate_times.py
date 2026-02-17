import pandas as pd
import yfinance as yf

df = pd.read_csv('val/trade_plan_EXECUTE.csv')
ticker = df['ticker'].iloc[0]
entry = df['entry'].iloc[0]
tp = df['tp_price'].iloc[0]
sl = df['sl_price'].iloc[0]
side = df['side'].iloc[0]
etth = df['etth_days_raw'].iloc[0]

print(f'=== VALIDACIÓN DE TIEMPOS PARA {ticker} ===')
print(f'Side: {side}')
print(f'Entry: ${entry:.2f}')
print(f'TP: ${tp:.2f} (distancia: +${tp-entry:.2f})')
print(f'SL: ${sl:.2f} (distancia: -${entry-sl:.2f})')
print(f'Tiempo estimado en plan: {etth:.4f} días = {int(etth*390)} min')

# Obtener precio actual
stock = yf.Ticker(ticker)
hist = stock.history(period='1d', interval='1m')
current = float(hist['Close'].iloc[-1])

dist_tp = abs(tp - current)
dist_sl = abs(current - sl)

print(f'\nPrecio actual: ${current:.2f}')
print(f'Distancia a TP: ${dist_tp:.2f}')
print(f'Distancia a SL: ${dist_sl:.2f}')

# Calcular velocidad
changes = hist['Close'].diff().dropna().tail(60)
velocity = changes.abs().mean()
high_low = hist['High'] - hist['Low']
high_close = abs(hist['High'] - hist['Close'].shift())
low_close = abs(hist['Low'] - hist['Close'].shift())
ranges = pd.concat([high_low, high_close, low_close], axis=1)
atr = ranges.max(axis=1).tail(14).mean()

combined = (velocity * 0.7) + (atr * 0.3)

print(f'\nVelocidad (60 min): ${velocity:.4f}/min')
print(f'ATR (14 períodos): ${atr:.4f}/min')
print(f'Velocidad combinada (70%+30%): ${combined:.4f}/min')

# Tiempo estimado a TP y SL
time_tp_min = dist_tp / combined if combined > 0 else 0
time_sl_min = dist_sl / combined if combined > 0 else 0

print(f'\n--- TIEMPOS CALCULADOS ---')
print(f'Tiempo a TP: {int(time_tp_min)} min ({time_tp_min/390:.4f} días)')
print(f'Tiempo a SL: {int(time_sl_min)} min ({time_sl_min/390:.4f} días)')
print(f'\n¿Son iguales TP y SL? {"SÍ" if abs(time_tp_min - time_sl_min) < 1 else "NO"}')
if time_sl_min > 0:
    print(f'Ratio: TP tarda {time_tp_min/time_sl_min:.2f}x más que SL')
