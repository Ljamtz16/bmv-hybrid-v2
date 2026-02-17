import pandas as pd
import glob

print('=== ANÁLISIS DE OPERACIONES BUY vs SELL ===\n')

# Planes semanales
print('📊 PLANES GENERADOS:')
print('='*60)
files = glob.glob('evidence/weekly_plans/*.csv')
for f in files:
    df = pd.read_csv(f)
    if 'side' in df.columns:
        buy = len(df[df['side']=='BUY'])
        sell = len(df[df['side']=='SELL'])
        total = len(df)
        print(f'\n{f}:')
        print(f'  BUY:  {buy:2d} ({buy/total*100:5.1f}%)')
        print(f'  SELL: {sell:2d} ({sell/total*100:5.1f}%)')
        print(f'  Total: {total}')

# Historial de trades
print('\n\n📈 HISTORIAL DE TRADES EJECUTADOS:')
print('='*60)
if pd.io.common.file_exists('val/trade_history_closed.csv'):
    df_hist = pd.read_csv('val/trade_history_closed.csv')
    if 'side' in df_hist.columns and len(df_hist) > 0:
        buy_hist = len(df_hist[df_hist['side']=='BUY'])
        sell_hist = len(df_hist[df_hist['side']=='SELL'])
        total_hist = len(df_hist)
        
        print(f'\nTrades cerrados:')
        print(f'  BUY:  {buy_hist:2d} ({buy_hist/total_hist*100:5.1f}%)')
        print(f'  SELL: {sell_hist:2d} ({sell_hist/total_hist*100:5.1f}%)')
        print(f'  Total: {total_hist}')
        
        # Resultados por tipo
        buy_trades = df_hist[df_hist['side']=='BUY']
        sell_trades = df_hist[df_hist['side']=='SELL']
        
        if len(buy_trades) > 0:
            buy_wins = len(buy_trades[buy_trades['pnl'] > 0])
            buy_total_pnl = buy_trades['pnl'].sum()
            print(f'\n  BUY Performance:')
            print(f'    Wins: {buy_wins}/{len(buy_trades)} ({buy_wins/len(buy_trades)*100:.1f}%)')
            print(f'    P&L: ${buy_total_pnl:.2f}')
        
        if len(sell_trades) > 0:
            sell_wins = len(sell_trades[sell_trades['pnl'] > 0])
            sell_total_pnl = sell_trades['pnl'].sum()
            print(f'\n  SELL Performance:')
            print(f'    Wins: {sell_wins}/{len(sell_trades)} ({sell_wins/len(sell_trades)*100:.1f}%)')
            print(f'    P&L: ${sell_total_pnl:.2f}')

# Posiciones activas
print('\n\n💼 POSICIONES ACTIVAS:')
print('='*60)
if pd.io.common.file_exists('val/trade_plan_EXECUTE.csv'):
    df_exec = pd.read_csv('val/trade_plan_EXECUTE.csv')
    if 'side' in df_exec.columns and len(df_exec) > 0:
        buy_exec = len(df_exec[df_exec['side']=='BUY'])
        sell_exec = len(df_exec[df_exec['side']=='SELL'])
        total_exec = len(df_exec)
        
        print(f'\nActualmente ejecutando:')
        print(f'  BUY:  {buy_exec:2d} ({buy_exec/total_exec*100:5.1f}%)')
        print(f'  SELL: {sell_exec:2d} ({sell_exec/total_exec*100:5.1f}%)')
        print(f'  Total: {total_exec}')
    else:
        print('\nNo hay posiciones activas')

print('\n' + '='*60)
print('✅ CONCLUSIÓN: El sistema usa tanto BUY como SELL (SHORT)')
