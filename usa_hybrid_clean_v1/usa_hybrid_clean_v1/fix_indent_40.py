#!/usr/bin/env python3
# Fix indentation in 40_make_trade_plan_intraday.py lines 290-310
import sys

with open('scripts/40_make_trade_plan_intraday.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix lines 299-310 (0-indexed)
lines[299] = '                    \n'
lines[300] = '                    # Verificar límites de exposure\n'
lines[301] = '                    if qty >= 1 and exposure <= target_max and exposure <= cash_left:\n'
lines[302] = '                        row[\'qty\'] = qty\n'
lines[303] = '                        row[\'exposure\'] = exposure\n'
lines[304] = '                        selected.append(row)\n'
lines[305] = '                        total_capital += exposure\n'
lines[306] = '                        print(f"  ✅ Fallback: {row[\'ticker\']} {row.get(\'direction\', \'LONG\')} @ ${price:.2f}, qty={qty}, exposure=${exposure:.2f}")\n'
lines[307] = '                        break  # Encontrado trade válido, salir del loop\n'
lines[308] = '                    else:\n'
lines[309] = '                        print(f"  ⚠️  Fallback candidato {row[\'ticker\']}: Exposure ${exposure:.2f} excede máximo ${target_max}, probando siguiente...")\n'
lines[310] = '                        continue  # Probar siguiente candidato\n'

with open('scripts/40_make_trade_plan_intraday.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('✅ Fixed indentation lines 300-311')
