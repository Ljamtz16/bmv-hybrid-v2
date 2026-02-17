import pandas as pd
from pathlib import Path

# Ruta al archivo descargado
parquet_path = Path(r"C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\data\us\intraday_15m\consolidated_15m.parquet")

print("📂 Leyendo archivo descargado de Alpaca...")
df = pd.read_parquet(parquet_path)

# Extraer fechas
df['date'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None).dt.date

print(f"\n📅 RANGO DE DATOS:")
print(f"  Desde: {df['date'].min()}")
print(f"  Hasta: {df['date'].max()}")
print(f"  Total barras: {len(df):,}")

print(f"\n📊 ÚLTIMAS 7 FECHAS:")
for date in sorted(df['date'].unique())[-7:]:
    count = len(df[df['date'] == date])
    print(f"  {date}: {count:>4} barras")

print(f"\n✅ Verificación completada")
