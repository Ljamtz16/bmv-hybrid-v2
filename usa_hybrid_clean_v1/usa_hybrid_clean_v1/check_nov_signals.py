import pandas as pd
import json

# Cargar política
pol = json.load(open('policies/Policy_H3_WF.json'))

# Cargar señales
sig = pd.read_csv('reports/forecast/2025-11/forecast_signals.csv', parse_dates=['date'])
nov = sig[(sig.date >= '2025-11-01') & (sig.gate_ok == 1)].copy()

print('=' * 60)
print('ANÁLISIS SEÑALES NOV 2025 vs POLICY H3 WF')
print('=' * 60)

print('\n📋 Filtros Policy WF:')
print(f"  min_prob_win: {pol['filters']['min_prob_win']:.2%}")
print(f"  min_ev_pct: {pol['filters']['min_ev_pct']:.2%}")
print(f"  atr_min: {pol['filters']['atr_min']:.3f}")
print(f"  atr_max: {pol['filters']['atr_max']:.3f}")
print(f"  TP: {pol['risk']['tp_pct']:.1%}")
print(f"  SL: {pol['risk']['sl_pct']:.1%}")

# Calcular p_tp_sl y EV manualmente
tp = pol['risk']['tp_pct']
sl = pol['risk']['sl_pct']
cost = pol['risk']['cost_pct']

nov['p_tp_sl'] = nov['prob_win']  # Simplificación (necesitaríamos TTH real)
nov['ev_gross'] = nov['prob_win'] * tp - (1 - nov['prob_win']) * sl
nov['ev_net'] = nov['ev_gross'] - cost

# Aplicar filtros
nov['pass_prob'] = nov['prob_win'] >= pol['filters']['min_prob_win']
nov['pass_ev'] = nov['ev_net'] >= pol['filters']['min_ev_pct']
nov['pass_atr'] = (nov['atr_pct'] >= pol['filters']['atr_min']) & (nov['atr_pct'] <= pol['filters']['atr_max'])
nov['pass_all'] = nov['pass_prob'] & nov['pass_ev'] & nov['pass_atr']

print('\n📊 Señales candidatas:')
print(nov[['date', 'ticker', 'prob_win', 'y_hat', 'atr_pct', 'ev_net']].to_string())

print('\n✅ Filtros aplicados:')
for _, row in nov.iterrows():
    print(f"\n{row['ticker']}:")
    print(f"  ✓ prob_win={row['prob_win']:.1%} (min {pol['filters']['min_prob_win']:.0%}): {'✅' if row['pass_prob'] else '❌'}")
    print(f"  ✓ EV_net={row['ev_net']:.2%} (min {pol['filters']['min_ev_pct']:.1%}): {'✅' if row['pass_ev'] else '❌'}")
    print(f"  ✓ ATR={row['atr_pct']:.3f} (rango {pol['filters']['atr_min']:.3f}-{pol['filters']['atr_max']:.3f}): {'✅' if row['pass_atr'] else '❌'}")

print('\n' + '=' * 60)
qualified = nov[nov['pass_all']]
print(f"🎯 RESULTADO: {len(qualified)} señales califican para trading")
if len(qualified) > 0:
    print('\n📈 Trades a ejecutar:')
    print(qualified[['date', 'ticker', 'prob_win', 'ev_net', 'y_hat']])
else:
    print('\n⚠️  Ninguna señal califica con los criterios de Policy_H3_WF')
print('=' * 60)
