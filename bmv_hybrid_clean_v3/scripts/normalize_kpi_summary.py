"""Normalize KPI summary JSON into a consistent schema and rewrite JSON/CSV/XLSX.
Run from repo root: python scripts/normalize_kpi_summary.py
"""
from pathlib import Path
import json
import pandas as pd

in_file = Path('reports/forecast/kpi_summary_jan_aug.json')
if not in_file.exists():
    print('Input file not found:', in_file)
    raise SystemExit(1)

with open(in_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

normalized = []
for e in data:
    n = {}
    # month
    n['month'] = e.get('month') or e.get('mes') or e.get('Month')
    # trades
    if 'trades' in e and isinstance(e['trades'], (int, float)):
        n['trades'] = int(e['trades'])
    elif 'trades_validos' in e:
        n['trades'] = int(e.get('trades_validos', 0))
    else:
        n['trades'] = int(e.get('Trades', 0))
    # net/gross pnl
    if 'net_pnl_sum' in e:
        n['net_pnl_sum'] = float(e['net_pnl_sum'])
    elif 'ganancia_total_mxn' in e:
        n['net_pnl_sum'] = float(e['ganancia_total_mxn'])
    elif 'PnL_sum' in e:
        n['net_pnl_sum'] = float(e['PnL_sum'])
    else:
        n['net_pnl_sum'] = float(e.get('net_pnl', 0.0) or 0.0)

    if 'gross_pnl_sum' in e:
        n['gross_pnl_sum'] = float(e['gross_pnl_sum'])
    else:
        # fallback: use net if gross not present
        n['gross_pnl_sum'] = n['net_pnl_sum']

    # rates
    n['tp_rate'] = float(e.get('tp_rate', e.get('tp_rate', 0.0) or 0.0))
    n['sl_rate'] = float(e.get('sl_rate', e.get('sl_rate', 0.0) or 0.0))
    n['horizon_rate'] = float(e.get('horizon_rate', e.get('horizon_rate', 0.0) or 0.0))

    # sizing and policy params
    n['per_trade_cash'] = float(e.get('per_trade_cash', e.get('per_trade_cash', 1000.0) or 1000.0))
    n['tp_pct'] = float(e.get('tp_pct', e.get('tp_pct', 0.0) or 0.0))
    n['sl_pct'] = float(e.get('sl_pct', e.get('sl_pct', 0.0) or 0.0))
    n['horizon_days'] = int(e.get('horizon_days', e.get('horizon_days', 0) or 0))

    # keep original raw for reference
    n['_raw'] = e
    normalized.append(n)

out_dir = Path('reports/forecast')
out_json = out_dir / 'kpi_summary_jan_aug_normalized.json'
out_csv = out_dir / 'kpi_summary_jan_aug_normalized.csv'
out_xlsx = out_dir / 'kpi_summary_jan_aug_normalized.xlsx'

with open(out_json, 'w', encoding='utf-8') as f:
    json.dump(normalized, f, ensure_ascii=False, indent=2)

# make DataFrame (drop _raw when saving CSV/XLSX)
df = pd.DataFrame([{k: v for k, v in r.items() if k != '_raw'} for r in normalized])
# ensure month_dt
try:
    df['month_dt'] = pd.to_datetime(df['month'].astype(str) + '-01')
except Exception:
    df['month_dt'] = pd.to_datetime(df['month'], errors='coerce')

# write CSV/XLSX
df.to_csv(out_csv, index=False)
with pd.ExcelWriter(out_xlsx, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='kpis', index=False)

print('Wrote normalized summary to:', out_json)
print('CSV:', out_csv)
print('XLSX:', out_xlsx)
