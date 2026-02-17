import pandas as pd

df = pd.read_csv('reports/forecast/2025-10/trades_detailed.csv')

print('=' * 60)
print('BACKTESTING MULTIDÍA Oct 2025')
print('=' * 60)
print(f'\nTrades ejecutados: {len(df)}')
print(f'Win rate: {(df.close_reason=="TP_HIT").mean()*100:.0f}%')
print(f'PnL total: ${df.pnl.sum():.2f}')
print(f'\nCapital inicial: $1100')
print(f'Capital final: ${1100 + df.pnl.sum():.2f}')
print(f'Return: {(df.pnl.sum()/1100)*100:.1f}%')

print('\n' + '=' * 60)
print('DETALLE DE TRADES:')
print('=' * 60)
print(df[['ticker','entry_dt','exit_dt','duration_days','close_reason','pnl','tp_pct']].to_string(index=False))
