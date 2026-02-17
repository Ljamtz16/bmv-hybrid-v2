"""Replace 2025-06 entry in kpi_summary_jan_aug.json with the standard kpi_policy.json from 2025-06 validation, then run normalize script.
Usage: python scripts/update_summary_replace_2025_06.py
"""
import json
from pathlib import Path

base = Path('reports/forecast')
summary = base / 'kpi_summary_jan_aug.json'
kpi_2025_06 = Path('reports/forecast/2025-06/validation/kpi_policy.json')

if not summary.exists():
    print('Summary not found:', summary)
    raise SystemExit(1)
if not kpi_2025_06.exists():
    print('kpi_policy.json for 2025-06 not found:', kpi_2025_06)
    raise SystemExit(1)

with open(summary, 'r', encoding='utf-8') as f:
    data = json.load(f)

with open(kpi_2025_06, 'r', encoding='utf-8') as f:
    k06 = json.load(f)

# find existing index for month 2025-06 (if any)
replaced = False
for i, e in enumerate(data):
    if isinstance(e, dict) and e.get('month') == '2025-06':
        data[i] = k06
        replaced = True
        break

if not replaced:
    # append if not found
    data.append(k06)

# write back
with open(summary, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('Replaced/Inserted 2025-06 in', summary)

# run normalization script to regenerate normalized files
import subprocess, sys
ret = subprocess.run([sys.executable, 'scripts/normalize_kpi_summary.py']).returncode
print('normalize_kpi_summary.py exitcode', ret)
