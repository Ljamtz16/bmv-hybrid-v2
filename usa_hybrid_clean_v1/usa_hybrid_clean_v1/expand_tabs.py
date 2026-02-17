#!/usr/bin/env python3
# Expandir tabs a espacios en 40_make_trade_plan_intraday.py
with open('scripts/40_make_trade_plan_intraday.py', 'r', encoding='utf-8') as f:
    content = f.read()

with open('scripts/40_make_trade_plan_intraday.py', 'w', encoding='utf-8') as f:
    f.write(content.expandtabs(4))

print('✅ Tabs expandidas a 4 espacios')
