"""Generate a PDF report with policy KPIs for a set of months.
Usage: python scripts/generate_policy_report.py --months 2025-01 2025-02 ... --out runs/final_run_2025_01_07/report_policy_kpis.pdf
If no months provided, defaults to 2025-01..2025-07 and writes into runs/final_run_2025_01_07/
"""
import argparse
from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

parser = argparse.ArgumentParser()
parser.add_argument('--months', nargs='*')
parser.add_argument('--out', default=None)
args = parser.parse_args()

months = args.months or ['2025-01','2025-02','2025-03','2025-04','2025-05','2025-06','2025-07']
base = Path('reports/forecast')
runs_dir = Path('runs/final_run_2025_01_07')
if not runs_dir.exists():
    runs_dir.mkdir(parents=True, exist_ok=True)

rows = []
for m in months:
    kpi_path = base / m / 'validation' / 'kpi_policy.json'
    # fallback options
    if not kpi_path.exists():
        kpi_path = base / m / 'validation' / 'kpi_policy_openlimits.json'
    if not kpi_path.exists():
        kpi_path = base / m / 'validation' / 'kpi_mxn.json'
    if not kpi_path.exists():
        print('Warning: no KPI found for', m)
        continue
    with open(kpi_path, 'r', encoding='utf-8') as f:
        k = json.load(f)
    # normalize keys
    row = {
        'month': m,
        'month_dt': pd.to_datetime(m + '-01'),
        'trades': int(k.get('trades', 0)),
        'net_pnl_sum': float(k.get('net_pnl_sum', k.get('ganancia_total_mxn', 0.0))),
        'gross_pnl_sum': float(k.get('gross_pnl_sum', k.get('gross_pnl_sum', 0.0) or 0.0)),
        'per_trade_cash': float(k.get('per_trade_cash', 0.0)),
        'tp_pct': float(k.get('tp_pct', 0.0)),
        'sl_pct': float(k.get('sl_pct', 0.0)),
        'horizon_days': int(k.get('horizon_days', 0)),
        'tp_rate': float(k.get('tp_rate', 0.0)),
        'sl_rate': float(k.get('sl_rate', 0.0)),
        'horizon_rate': float(k.get('horizon_rate', 0.0)),
    }
    rows.append(row)

if not rows:
    print('No KPI rows collected; aborting')
    raise SystemExit(1)

df = pd.DataFrame(rows).sort_values('month_dt')
# save copy
json_out = runs_dir / 'report_policy_kpis_source.json'
df.to_json(json_out, orient='records', date_format='iso')

csv_out = runs_dir / 'report_policy_kpis_source.csv'
df.to_csv(csv_out, index=False)

# Create PDF
pdf_path = Path(args.out) if args.out else runs_dir / 'report_policy_kpis.pdf'
with PdfPages(pdf_path) as pdf:
    # Page 1: title + summary table
    fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4
    ax.axis('off')
    ax.set_title('Policy KPI report (Jan - Jul 2025)', fontsize=16, pad=20)
    # draw table
    table_df = df[['month','trades','net_pnl_sum','gross_pnl_sum','per_trade_cash','tp_pct','sl_pct','horizon_days']].copy()
    table_df['net_pnl_sum'] = table_df['net_pnl_sum'].map('{:,.2f}'.format)
    table_df['gross_pnl_sum'] = table_df['gross_pnl_sum'].map('{:,.2f}'.format)
    table_df['per_trade_cash'] = table_df['per_trade_cash'].map('{:,.0f}'.format)
    table_df.columns = ['Month','Trades','Net PnL (MXN)','Gross PnL (MXN)','Per trade cash','TP %','SL %','H days']
    ax.table(cellText=table_df.values, colLabels=table_df.columns, loc='center', cellLoc='center')
    pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

    # Page 2: Net PnL line
    fig, ax = plt.subplots(figsize=(11,6))
    ax.plot(df['month_dt'], df['net_pnl_sum'], marker='o', linestyle='-')
    ax.set_title('Net PnL by month')
    ax.set_ylabel('Net PnL (MXN)')
    ax.set_xlabel('Month')
    ax.grid(True)
    pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

    # Page 3: Trades bar
    fig, ax = plt.subplots(figsize=(11,6))
    ax.bar(df['month_dt'].dt.strftime('%Y-%m'), df['trades'], color='C2')
    ax.set_title('Trades per month')
    ax.set_ylabel('Trades')
    ax.set_xlabel('Month')
    ax.grid(axis='y')
    pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

    # Page 4: TP/SL rates and horizon rates table
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    ax.axis('off')
    rates = df[['month','tp_rate','sl_rate','horizon_rate']].copy()
    rates['tp_rate'] = (rates['tp_rate']*100).map('{:.2f}%'.format)
    rates['sl_rate'] = (rates['sl_rate']*100).map('{:.2f}%'.format)
    rates['horizon_rate'] = (rates['horizon_rate']*100).map('{:.2f}%'.format)
    ax.table(cellText=rates.values, colLabels=['Month','TP rate','SL rate','Horizon rate'], loc='center')
    ax.set_title('TP/SL/Horizon rates', pad=20)
    pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

print('PDF written to', pdf_path)
print('Also saved CSV/JSON to', runs_dir)
