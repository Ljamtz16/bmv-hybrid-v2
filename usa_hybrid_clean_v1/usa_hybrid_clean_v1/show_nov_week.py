import pandas as pd
import json
import os

base = 'reports/forecast/2025-11/'

print('=' * 70)
print('PREDICCIÓN SEMANA NOV 4-7 (SISTEMA H3 MULTIDÍA)')
print('=' * 70)

# Leer trades
trades_file = base + 'trades_detailed.csv'
if os.path.exists(trades_file):
    trades = pd.read_csv(trades_file)
    print(f'\n📊 Total trades simulados: {len(trades)}')
    
    if len(trades) > 0:
        print('\n📋 PLAN DE TRADES:')
        print('-' * 70)
        for _, t in trades.iterrows():
            print(f"\n🎯 {t['ticker']} - {t['entry_date']}")
            print(f"   Entry: ${t['entry_price']:.2f}")
            tp_pct = t.get('tp_pct_suggested', 0.065)
            sl_pct = t.get('sl_pct_suggested', 0.008)
            print(f"   TP sugerido: ${t['entry_price']*(1+tp_pct):.2f} (+{tp_pct*100:.1f}%)")
            print(f"   SL sugerido: ${t['entry_price']*(1-sl_pct):.2f} (-{sl_pct*100:.1f}%)")
            print(f"   Prob win: {t['prob_win']:.1%}")
            print(f"   y_hat: {t['y_hat']:.3f}")
            if 'reason' in t and pd.notna(t['reason']):
                print(f"   Cierre: {t['reason']} → ${t['exit_price']:.2f} (PnL: ${t['pnl']:.2f})")
        
        # KPIs
        kpi_file = base + 'kpi_all.json'
        if os.path.exists(kpi_file):
            kpi = json.load(open(kpi_file))
            print('\n' + '=' * 70)
            print('💰 KPIs (BACKTEST):')
            print('-' * 70)
            print(f"  Win rate: {kpi.get('win_rate', 0):.1%}")
            print(f"  Total PnL: ${kpi.get('total_pnl', 0):.2f}")
            print(f"  Return: {kpi.get('return_pct', 0):.1%}")
            print(f"  Total trades: {kpi.get('total_trades', 0)}")
    else:
        print('\n⚠️  No hay trades en el backtest')
else:
    print('\n❌ No se generó archivo de trades')

# Señales originales
signals_file = base + 'forecast_signals.csv'
if os.path.exists(signals_file):
    sig = pd.read_csv(signals_file, parse_dates=['date'])
    nov = sig[sig['date'] >= '2025-11-01']
    print('\n' + '=' * 70)
    print('📡 SEÑALES GENERADAS:')
    print('-' * 70)
    print(f"Total señales Nov: {len(nov)}")
    print(f"Gate OK: {nov['gate_ok'].sum()}")
    print(f"\nTop 5 por prob_win:")
    top = nov.nlargest(5, 'prob_win')[['date', 'ticker', 'prob_win', 'y_hat', 'gate_ok']]
    print(top.to_string())

print('\n' + '=' * 70)
print('⚠️  NOTA: Solo tenemos datos hasta Nov 3, 2025')
print('   Para predicciones completas Nov 4-7, esperar datos diarios')
print('=' * 70)
