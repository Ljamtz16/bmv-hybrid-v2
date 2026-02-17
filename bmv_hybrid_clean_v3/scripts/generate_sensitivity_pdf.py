"""Generate a sensitivity PDF comparing KPIs produced in runs/ for 2025-07.
Writes PDF to runs/final_run_2025_01_07/report_sensitivity_2025-07.pdf
"""
import json
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

runs = Path('runs')
files = list(runs.glob('kpi_*.json')) + list(runs.glob('kpi_sens_*_2025-07.json'))
# filter relevant files
files = [f for f in files if f.is_file() and '2025-07' in f.name]
rows = []
for f in files:
    try:
        with open(f,'r',encoding='utf-8') as fh:
            k = json.load(fh)
    except Exception:
        continue
    name = f.stem
    rows.append({
        'run_file': name,
        'trades': int(k.get('trades',0)),
        'net_pnl_sum': float(k.get('net_pnl_sum',0.0)),
        'gross_pnl_sum': float(k.get('gross_pnl_sum',0.0)),
        'per_trade_cash': float(k.get('per_trade_cash',0.0)),
        'tp_pct': float(k.get('tp_pct',0.0)),
        'sl_pct': float(k.get('sl_pct',0.0)),
        'horizon_days': int(k.get('horizon_days',0))
    })

if not rows:
    print('No KPI files found for 2025-07 in runs/')
    raise SystemExit(1)

df = pd.DataFrame(rows).sort_values('net_pnl_sum', ascending=False)
out_pdf = runs / 'final_run_2025_01_07' / 'report_sensitivity_2025-07.pdf'
with PdfPages(out_pdf) as pdf:
    # table
    fig, ax = plt.subplots(figsize=(8.27,11.69))
    ax.axis('off')
    tbl = df[['run_file','trades','net_pnl_sum','gross_pnl_sum','per_trade_cash']].copy()
    tbl['net_pnl_sum'] = tbl['net_pnl_sum'].map('{:,.2f}'.format)
    tbl['gross_pnl_sum'] = tbl['gross_pnl_sum'].map('{:,.2f}'.format)
    ax.table(cellText=tbl.values, colLabels=tbl.columns, loc='center')
    ax.set_title('Sensitivity results (2025-07)')
    pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

    # bar net pnl
    fig, ax = plt.subplots(figsize=(11,6))
    ax.bar(df['run_file'], df['net_pnl_sum'], color='C0')
    ax.set_title('Net PnL by run (2025-07)')
    ax.set_ylabel('Net PnL (MXN)')
    ax.set_xlabel('Run')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

print('Wrote sensitivity PDF to', out_pdf)
print(df[['run_file','trades','net_pnl_sum','per_trade_cash']])
