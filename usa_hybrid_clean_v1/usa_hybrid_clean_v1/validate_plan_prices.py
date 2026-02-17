import pandas as pd

# Cargar plan forward-looking
plan = pd.read_csv('reports/forecast/2025-11/trade_plan_tth.csv')
plan['date'] = pd.to_datetime(plan['date'], errors='coerce')
plan3 = plan.head(3).copy()

# Cargar precios actuales
prices = pd.read_csv('data/us/ohlcv_us_daily.csv')
prices['date'] = pd.to_datetime(prices['date'])
latest_prices = prices.groupby('ticker').tail(1)[['ticker', 'date', 'close']]

print('='*80)
print('🔍 VALIDACIÓN: PLAN FORWARD-LOOKING vs PRECIOS ACTUALES')
print('='*80)

for _, row in plan3.iterrows():
    ticker = row['ticker']
    entry = row['entry_price']
    plan_date = row['date']
    side = row.get('side', 'BUY')
    
    current_info = latest_prices[latest_prices['ticker'] == ticker]
    if len(current_info) > 0:
        current_price = current_info['close'].values[0]
        current_date = current_info['date'].values[0]
        
        # Calcular diferencia según side
        if side == 'BUY':
            diff_pct = ((current_price - entry) / entry) * 100
        else:  # SHORT
            diff_pct = ((entry - current_price) / entry) * 100
        
        status = '✅ VÁLIDO' if abs(diff_pct) < 5 else '⚠️  DESACTUALIZADO'
        side_emoji = '📈' if side == 'BUY' else '📉'
        
        print(f'\n{ticker} {side_emoji} {side}:')
        print(f'  Plan date:    {plan_date.date()}')
        print(f'  Entry price:  ${entry:.2f}')
        print(f'  Current date: {pd.to_datetime(current_date).date()}')
        print(f'  Current price: ${current_price:.2f}')
        print(f'  Diferencia:   {diff_pct:+.2f}% {status}')
        
        # Calcular TP y SL según side
        tp_pct = row.get('tp_pct', 0.04)
        sl_pct = row.get('sl_pct', 0.02)
        
        if side == 'BUY':
            tp_price = entry * (1 + tp_pct)
            sl_price = entry * (1 - sl_pct)
            print(f'  TP objetivo:  ${tp_price:.2f} (+{tp_pct*100:.1f}%) ⬆️')
            print(f'  SL stop:      ${sl_price:.2f} (-{sl_pct*100:.1f}%) ⬇️')
        else:  # SHORT
            tp_price = entry * (1 - tp_pct)
            sl_price = entry * (1 + sl_pct)
            print(f'  TP objetivo:  ${tp_price:.2f} (-{tp_pct*100:.1f}%) ⬇️')
            print(f'  SL stop:      ${sl_price:.2f} (+{sl_pct*100:.1f}%) ⬆️')
        
        # Ver si ya tocó TP o SL según side
        if side == 'BUY':
            if current_price >= tp_price:
                pnl = ((current_price-entry)/entry)*100
                print(f'  💰 ¡TP ALCANZADO! (+{pnl:.2f}%)')
            elif current_price <= sl_price:
                pnl = ((current_price-entry)/entry)*100
                print(f'  🛑 SL ALCANZADO ({pnl:.2f}%)')
            else:
                progress = ((current_price - entry) / (tp_price - entry)) * 100
                remaining = ((tp_price - current_price) / current_price) * 100
                print(f'  📊 En progreso {progress:.1f}% (falta {remaining:+.2f}% para TP)')
        else:  # SHORT
            if current_price <= tp_price:
                pnl = ((entry-current_price)/entry)*100
                print(f'  � ¡TP ALCANZADO! (+{pnl:.2f}%)')
            elif current_price >= sl_price:
                pnl = ((entry-current_price)/entry)*100
                print(f'  🛑 SL ALCANZADO ({pnl:.2f}%)')
            else:
                progress = ((entry - current_price) / (entry - tp_price)) * 100
                remaining = ((current_price - tp_price) / current_price) * 100
                print(f'  📊 En progreso {progress:.1f}% (falta {remaining:+.2f}% para TP)')

print('\n' + '='*80)
