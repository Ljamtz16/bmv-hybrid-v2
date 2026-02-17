# scripts/run_jan_aug_validate.py
"""
Ejecuta forecast+validate para los meses 2025-01 .. 2025-08.
- Aplica open-limits y usa la política wf_box si existe.
- Recolecta kpi_policy.json por mes (o variantes) y guarda resumen JSON/CSV/Excel.
- Genera un gráfico month vs net_profit.

Uso: desde la raíz del repo:
    python scripts/run_jan_aug_validate.py

Opciones (editar variables abajo): python_bin, base_cmd, months, capital

"""
from pathlib import Path
import subprocess, json, os, sys
import pandas as pd
import matplotlib.pyplot as plt

# ----------------- configuración -----------------
months = [
    "2025-01", "2025-02", "2025-03", "2025-04",
    "2025-05", "2025-06", "2025-07", "2025-08"
]

# intenta usar venv por defecto, si no existe usa sys.executable
venv_py = Path('.venv') / 'Scripts' / 'python.exe'
python = str(venv_py if venv_py.exists() else sys.executable)

# base comando: usa 12_forecast_and_validate.py con flags que has usado antes
base_cmd = [
    python, "scripts/12_forecast_and_validate.py",
    "--apply-open-limits", "--max-open", "5",
    "--per-trade-cash", "2000", "--budget", "10000",
    "--use-wf-policy",
    "--wf-policy-file", "wf_box/reports/forecast/policy_selected_walkforward.csv"
]

# output paths
out_dir = Path('reports/forecast')
out_dir.mkdir(parents=True, exist_ok=True)
summary_json = out_dir / 'kpi_summary_jan_aug.json'
summary_csv = out_dir / 'kpi_summary_jan_aug.csv'
summary_xlsx = out_dir / 'kpi_summary_jan_aug.xlsx'
plot_png = out_dir / 'kpi_summary_jan_aug.png'

# capital para cálculo ROI (puedes cambiarlo)
capital = 10000.0

# ----------------- ejecución -----------------
results = []
failed = []

for m in months:
    print(f"\n🚀 Ejecutando mes {m}")
    cmd = base_cmd + ["--month", m]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(f"❌ Falló la ejecución para {m} (returncode={proc.returncode}). Intento fallback sin wf-policy.")
        # intentar fallback: correr el flujo sin --use-wf-policy / --wf-policy-file
        fallback_cmd = [
            python, "scripts/12_forecast_and_validate.py",
            "--apply-open-limits", "--max-open", "5",
            "--per-trade-cash", "2000", "--budget", "10000",
            "--month", m
        ]
        proc2 = subprocess.run(fallback_cmd)
        if proc2.returncode != 0:
            print(f"❌ Fallback también falló para {m} (returncode={proc2.returncode}). Saltando mes.")
            failed.append({"month": m, "reason": f"base_returncode={proc.returncode}, fallback_returncode={proc2.returncode}"})
            continue
        else:
            print(f"🔁 Fallback sin wf-policy completado para {m} (returncode={proc2.returncode}).")

    # buscar KPI generado (varios nombres posibles)
    kpi_paths = [
        out_dir / m / 'validation' / 'kpi_policy.json',
        out_dir / m / 'validation' / 'kpi_policy_openlimits.json',
        out_dir / m / 'validation' / 'kpi_policy_openlimits_2500.json',
        out_dir / m / 'validation' / 'kpi_mxn.json',
    ]
    found = None
    for p in kpi_paths:
        if p.exists():
            found = p
            break

    if not found:
        print(f"⚠️ No se encontró KPI esperado para {m}. Busqué: {[str(p) for p in kpi_paths]}")
        failed.append({"month": m, "reason": "kpi_not_found", "searched": [str(p) for p in kpi_paths]})
        continue

    try:
        with open(found, 'r', encoding='utf-8') as f:
            k = json.load(f)
            # normalizar campos mínimos
            k.setdefault('month', m)
            # si net_pnl_sum no existe, intentar gross_pnl_sum o net_pnl
            if 'net_pnl_sum' not in k and 'gross_pnl_sum' in k:
                k['net_pnl_sum'] = k['gross_pnl_sum']
            if 'trades' not in k:
                k['trades'] = int(k.get('trades', 0))
            results.append(k)
            print(f"✅ KPI cargado para {m} desde {found.name}")
    except Exception as e:
        print(f"❌ Error leyendo {found}: {e}")
        continue

# ----------------- consolidar y guardar -----------------
if not results:
    print("⚠️ No se recopilaron KPIs. Asegúrate de que los scripts se ejecuten correctamente.")
    sys.exit(1)

# convertir a DataFrame
df = pd.DataFrame(results)
# normalizar month a datetime (usar primer día)
try:
    df['month_dt'] = pd.to_datetime(df['month'].astype(str) + '-01')
except Exception:
    df['month_dt'] = pd.to_datetime(df['month'], errors='coerce')

# asegurar columnas numéricas
for col in ['net_pnl_sum', 'gross_pnl_sum', 'trades']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

# métricas adicionales
df['net_profit'] = df['net_pnl_sum']
df['roi_pct'] = (df['net_profit'] / float(capital)) * 100.0

# ordenar por fecha
df = df.sort_values('month_dt')

# guardar JSON/CSV/XLSX
with open(summary_json, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

df.to_csv(summary_csv, index=False)
# Excel con hoja detallada
with pd.ExcelWriter(summary_xlsx, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='kpis', index=False)

# guardar meses fallidos para diagnóstico
failed_json = out_dir / 'kpi_failed_months.json'
with open(failed_json, 'w', encoding='utf-8') as f:
    json.dump(failed, f, ensure_ascii=False, indent=2)

# ----------------- plot -----------------
plt.figure(figsize=(10,5))
plt.plot(df['month_dt'], df['net_profit'], marker='o')
plt.title('Net profit by month (Jan-Aug 2025)')
plt.xlabel('Month')
plt.ylabel('Net profit (MXN)')
plt.grid(True)
plt.tight_layout()
plt.savefig(plot_png)
print(f"\n✅ Resumen guardado: {summary_json}, {summary_csv}, {summary_xlsx}")
print(f"✅ Gráfico guardado: {plot_png}")
print('\nHecho.')
if failed:
    print('\n⚠️ Algunos meses fallaron durante la ejecución. Revisa reports/forecast/kpi_failed_months.json para detalles:')
    for e in failed:
        print(f" - {e.get('month')}: {e.get('reason')}")
