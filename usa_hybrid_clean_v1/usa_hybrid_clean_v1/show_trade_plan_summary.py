import pandas as pd

df = pd.read_csv('reports/forecast/2025-11/trade_plan_tth.csv')

print('='*60)
print('🎯 TRADE PLAN SEMANA 1 - NOVIEMBRE 2025')
print('='*60)
print(f'\n📊 Señales: {len(df)}')
print(f'💰 Capital total: ${df["exposure"].sum():.2f}')
print(f'📈 Win rate promedio: {df["prob_win"].mean()*100:.1f}%')
print(f'⏱️  ETTH promedio: {df["etth_first_event"].mean():.1f} días')
print(f'🎲 P(TP≺SL) promedio: {df["p_tp_before_sl"].mean()*100:.1f}%')

print('\n🔝 TOP 3 TRADES:')
for i, r in df.head(3).iterrows():
    print(f'{i+1}. {r["ticker"]:5s} | Entry: ${r["entry_price"]:.2f} | TP: +{r["tp_pct"]*100:.1f}% | Prob: {r["prob_win"]*100:.0f}% | Qty: {int(r["qty"])}')
