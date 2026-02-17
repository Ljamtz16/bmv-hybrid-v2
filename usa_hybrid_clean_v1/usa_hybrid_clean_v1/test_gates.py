#!/usr/bin/env python3
"""
Test and display results of Ticker Gate + Param Gate
"""
import json

print('\n' + '='*70)
print('RESULTS: TICKER GATE + PARAM GATE (Marzo 2025)')
print('='*70)

# Ticker Gate
with open('evidence/ticker_gate_mar2025/ticker_gate.json') as f:
    tg = json.load(f)

selected_tickers = tg['selected_tickers']
print(f'\n🎯 TICKER GATE (Top-4 seleccionados):')
for i, tk in enumerate(selected_tickers, 1):
    for r in tg['ranking']:
        if r['ticker'] == tk:
            m = r['metrics']
            score = m['score']
            ev = m['ev']
            tp_rate = m['tp_rate']
            print(f'   {i}. {tk}: Score={score:7.4f} | EV=${ev:6.4f} | TP={tp_rate:5.1%}')
            break

# Param Gate
with open('evidence/param_gate_mar2025/tp_sl_choice.json') as f:
    pg = json.load(f)

choice = pg['final_choice']
tp_pct = choice['tp_pct']
sl_pct = choice['sl_pct']
ratio = choice['tp_sl_ratio']

print(f'\n⚙️ PARAM GATE (TP/SL elegidos):')
print(f'   TP: {tp_pct*100:4.1f}%')
print(f'   SL: {sl_pct*100:4.1f}%')
print(f'   TP/SL Ratio: {ratio:4.2f}')

# Top-5 combinaciones
print(f'\n   Top-5 combinaciones TP/SL:')
for i, combo in enumerate(pg['grid_results'][:5], 1):
    tp = combo['tp_pct']
    sl = combo['sl_pct']
    score = combo['metrics']['score']
    tp_rate = combo['metrics']['tp_rate']
    print(f'   {i}. TP={tp*100:4.1f}% | SL={sl*100:4.1f}% | Score={score:7.4f} | TP Rate={tp_rate:5.1%}')

print('\n' + '='*70)
print('COMPARATIVA CON CONFIGS ANTERIORES')
print('='*70)
print('\n                    | TP    | SL    | Ratio | Esperado TP Rate')
print('-' * 70)
print(f'Anterior (FAST)     | 2.0%  | 1.2%  | 1.67  | 1.3%')
print(f'Anterior (TP=0.8%)  | 0.8%  | 1.2%  | 0.67  | 56.4%')
print(f'MC Param Gate       | {tp_pct*100:4.1f}% | {sl_pct*100:4.1f}%  | {ratio:4.2f}  | ?%')
print('\n'+'='*70)
