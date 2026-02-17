"""
Snapshot the reports for a list of months into a timestamped run folder under runs/
Usage: python scripts/snapshot_results_run.py --months 2025-01 2025-02 ... --label mylabel
If no months provided, defaults to 2025-01..2025-07
"""
import argparse
from pathlib import Path
import shutil
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--months', nargs='*')
parser.add_argument('--label', default=None)
args = parser.parse_args()

months = args.months or [
    '2025-01','2025-02','2025-03','2025-04','2025-05','2025-06','2025-07'
]

base = Path('reports/forecast')
runs_dir = Path('runs')
runs_dir.mkdir(exist_ok=True)

now = datetime.now().strftime('%Y%m%d_%H%M%S')
label = args.label or f'snapshot_2025_01_07_{now}'
dest = runs_dir / label
if dest.exists():
    print('Destination exists, aborting:', dest)
    raise SystemExit(1)

dest.mkdir(parents=True)

copied = []
for m in months:
    src = base / m
    if not src.exists():
        print('Warning: source month not found, skipping', src)
        continue
    # copy the whole month folder
    dst = dest / m
    shutil.copytree(src, dst)
    copied.append(str(dst))

# also copy consolidated summaries if present
for f in ['kpi_summary_jan_aug.json','kpi_summary_jan_aug.csv','kpi_summary_jan_aug.xlsx','kpi_summary_jan_aug_normalized.json','kpi_summary_jan_aug_normalized.csv','kpi_summary_jan_aug_normalized.xlsx','kpi_failed_months.json']:
    s = base / f
    if s.exists():
        shutil.copy2(s, dest / s.name)
        copied.append(str(dest / s.name))

print('Snapshot completed ->', dest)
print('Copied items:')
for c in copied:
    print(' -', c)
