import pandas as pd
from pathlib import Path

# Carpeta base donde están los reportes
base_dir = Path("reports/forecast")

# Patrón de búsqueda: busca recursivamente archivos validation_trades_*.csv
csv_files = list(base_dir.rglob("validation_trades_*.csv"))

if not csv_files:
    print("⚠️ No se encontraron archivos 'validation_trades_*.csv' bajo reports/forecast/")
    raise SystemExit

summary_rows = []

print(f"📂 Archivos encontrados: {len(csv_files)}\n")

for csv_path in sorted(csv_files):
    try:
        # Leemos solo la primera línea para obtener encabezados (más rápido)
        with open(csv_path, "r", encoding="utf-8") as f:
            header_line = f.readline().strip()
        columns = header_line.split(",")
        columns = [c.strip() for c in columns if c.strip()]

        print(f"📄 {csv_path}")
        print(f"   Columnas ({len(columns)}): {columns}\n")

        summary_rows.append({
            "csv_path": str(csv_path),
            "num_columns": len(columns),
            "columns": ", ".join(columns)
        })

    except Exception as e:
        print(f"❌ Error leyendo {csv_path}: {e}")

# Guardar resumen en un CSV global
summary_df = pd.DataFrame(summary_rows)
out_path = base_dir / "_csv_headers_summary.csv"
summary_df.to_csv(out_path, index=False, encoding="utf-8")

print(f"\n✅ Resumen guardado en: {out_path}")
