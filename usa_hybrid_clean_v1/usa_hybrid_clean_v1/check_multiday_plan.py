import pandas as pd

df = pd.read_csv('reports/forecast/2025-10/trade_plan.csv')
print('=' * 60)
print('PLAN MULTIDÍA Oct 2025 - SISTEMA H3')
print('=' * 60)
print(f'\nTotal trades: {len(df)}')
print(f'Capital total: ${df.exposure.sum():.0f}')
print(f'Prob win media: {df.prob_win.mean():.1f}%')
print(f'Horizonte: {df.horizon_days.iloc[0]} días')
print(f'\nPolítica: {df.policy.iloc[0]}')
print('\n' + '=' * 60)

for i, row in df.iterrows():
    tp_pct = (row.tp_price/row.entry - 1) * 100
    sl_pct = (row.sl_price/row.entry - 1) * 100
    print(f'\nTrade #{i+1}: {row.ticker} {row.side}')
    print(f'  Entry: ${row.entry:.2f}')
    print(f'  TP: ${row.tp_price:.2f} (+{tp_pct:.1f}%)')
    print(f'  SL: ${row.sl_price:.2f} ({sl_pct:.1f}%)')
    print(f'  Qty: {row.qty:.0f} shares')
    print(f'  Exposure: ${row.exposure:.0f}')
    print(f'  Prob win: {row.prob_win:.1f}%')
    print(f'  Y_hat: {row.y_hat:.3f}')

print('\n' + '=' * 60)
