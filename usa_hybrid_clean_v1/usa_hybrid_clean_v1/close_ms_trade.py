import pandas as pd
from datetime import datetime

# Datos de la posición MS del plan STANDARD
ticker = 'MS'
side = 'BUY'
entry = 180.26
exit_price = 182.90
tp_price = 183.15
sl_price = 178.46
qty = 2
exposure = 360.53
prob_win = 0.5423

# Calcular P&L
pnl = (exit_price - entry) * qty
pnl_pct = ((exit_price - entry) / entry) * 100

# Crear registro de cierre
closed_trade = {
    'ticker': ticker,
    'side': side,
    'entry': entry,
    'exit': exit_price,
    'tp_price': tp_price,
    'sl_price': sl_price,
    'qty': qty,
    'exposure': exposure,
    'prob_win': prob_win,
    'exit_reason': 'MANUAL_PROFIT',
    'pnl': round(pnl, 2),
    'pnl_pct': round(pnl_pct, 2),
    'closed_at': datetime.now().isoformat(),
    'date': datetime.now().strftime('%d/%m/%Y'),
    'trade_id': f'STD-{ticker}-2026-01-29',
    'plan_type': 'STANDARD'
}

# Leer historial existente
try:
    df_hist = pd.read_csv('val/trade_history_closed.csv')
except:
    df_hist = pd.DataFrame()

# Agregar nuevo cierre
df_new = pd.DataFrame([closed_trade])
df_hist = pd.concat([df_hist, df_new], ignore_index=True)

# Guardar
df_hist.to_csv('val/trade_history_closed.csv', index=False)

print('✅ Posición MS cerrada con GANANCIA')
print(f'Entry: ${entry:.2f}')
print(f'Exit:  ${exit_price:.2f}')
print(f'P&L:   ${pnl:.2f} ({pnl_pct:.2f}%)')
print(f'\nTrade agregado al historial: val/trade_history_closed.csv')
