import json

with open('evidence/dynamic_gate_mar2025/dynamic_gate.json') as f:
    dg = json.load(f)

print('\n' + '='*70)
print('📊 RESUMEN DYNAMIC GATE - MARZO 2025')
print('='*70)

print(f'\n🔄 Frecuencia: {dg["config"]["rebalance_freq"]}')
print(f'📌 Top-K: {dg["config"]["top_k"]}')
print(f'🔀 Max Rotación: {dg["config"]["max_rotation"]}')

print('\n📅 EVOLUCIÓN DEL PORTAFOLIO:')
print('='*70)

for rb in dg['rebalance_history']:
    num = rb['rebalance_number']
    date = rb['rebalance_date']
    portfolio = rb['portfolio']
    changes = rb['changes']
    
    print(f'\n{num}. {date}')
    print(f'   Portafolio: {" | ".join(portfolio)}')
    
    if changes['added']:
        print(f'   ➕ Agregados: {", ".join(changes["added"])}')
    if changes['dropped']:
        print(f'   ➖ Eliminados: {", ".join(changes["dropped"])}')
    if not changes['added'] and not changes['dropped'] and num > 1:
        print(f'   ✅ Sin cambios')

print('\n' + '='*70)
print('🏆 PORTAFOLIO FINAL:', ' | '.join(dg['final_portfolio']))
print('='*70)

# Count total rotations
total_added = sum(len(rb['changes']['added']) for rb in dg['rebalance_history'][1:])
total_dropped = sum(len(rb['changes']['dropped']) for rb in dg['rebalance_history'][1:])

print(f'\n📊 ESTADÍSTICAS:')
print(f'   Total rotaciones: {total_added} entradas / {total_dropped} salidas')
print(f'   Rebalances con cambios: {sum(1 for rb in dg["rebalance_history"][1:] if rb["changes"]["added"] or rb["changes"]["dropped"])}/{len(dg["rebalance_history"])-1}')

# Compare with static gate
print('\n' + '='*70)
print('📊 COMPARACIÓN: DYNAMIC vs STATIC GATE')
print('='*70)

try:
    with open('evidence/ticker_gate_mar2025/ticker_gate.json') as f:
        static = json.load(f)
    
    static_tickers = static['selected_tickers']
    dynamic_final = dg['final_portfolio']
    
    print(f'\nStatic Gate (fijo todo el mes):')
    print(f'   {" | ".join(static_tickers)}')
    
    print(f'\nDynamic Gate (final):')
    print(f'   {" | ".join(dynamic_final)}')
    
    common = set(static_tickers) & set(dynamic_final)
    only_static = set(static_tickers) - set(dynamic_final)
    only_dynamic = set(dynamic_final) - set(static_tickers)
    
    print(f'\n✅ Coinciden: {", ".join(common) if common else "Ninguno"}')
    print(f'🔵 Solo Static: {", ".join(only_static) if only_static else "Ninguno"}')
    print(f'🟢 Solo Dynamic: {", ".join(only_dynamic) if only_dynamic else "Ninguno"}')
    
except FileNotFoundError:
    print('\n⚠️ No se encontró static gate para comparar')
