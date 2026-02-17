import pandas as pd

# Cargar archivo
file_path = "C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet"
df = pd.read_parquet(file_path)

print("="*70)
print("📊 ANÁLISIS COMPLETO: consolidated_15m.parquet")
print("="*70)

print(f"\n📁 Archivo: {file_path}")
print(f"📦 Shape: {df.shape} (rows, columns)")
print(f"💾 Tamaño en memoria: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

print("\n" + "="*70)
print("📋 ESTRUCTURA")
print("="*70)
print(f"\nColumnas: {df.columns.tolist()}")
print(f"\nTipos de datos:")
for col in df.columns:
    print(f"  {col}: {df[col].dtype}")

print("\n" + "="*70)
print("🎯 TICKERS DISPONIBLES")
print("="*70)
tickers = sorted(df['ticker'].unique())
print(f"\nTotal tickers: {len(tickers)}")
print(f"\nTickers: {', '.join(tickers)}")

print("\n" + "="*70)
print("📅 RANGO DE FECHAS")
print("="*70)
print(f"\nInicio: {df['timestamp'].min()}")
print(f"Fin: {df['timestamp'].max()}")
print(f"Duración: {(df['timestamp'].max() - df['timestamp'].min()).days} días")

print("\n" + "="*70)
print("📊 OBSERVACIONES POR TICKER")
print("="*70)
counts = df['ticker'].value_counts().sort_index()
print(f"\n{'Ticker':<8} {'Registros':>12} {'Porcentaje':>10}")
print("-"*35)
for ticker, count in counts.items():
    pct = count / len(df) * 100
    print(f"{ticker:<8} {count:>12,} {pct:>9.1f}%")

print("\n" + "="*70)
print("📈 CALIDAD DE DATOS")
print("="*70)
print(f"\nValores nulos por columna:")
for col in df.columns:
    nulls = df[col].isna().sum()
    if nulls > 0:
        print(f"  {col}: {nulls:,} ({nulls/len(df)*100:.2f}%)")
    else:
        print(f"  {col}: 0 ✅")

print("\n" + "="*70)
print("🔍 EJEMPLO DE DATOS")
print("="*70)
print("\nPrimeras 5 filas:")
print(df.head())

print("\n" + "="*70)
print("💡 ANÁLISIS DE COBERTURA TEMPORAL")
print("="*70)

# Verificar cobertura por mes
df['month'] = pd.to_datetime(df['timestamp']).dt.to_period('M')
monthly_coverage = df.groupby(['ticker', 'month']).size().unstack(fill_value=0)

print(f"\nMeses con datos:")
months = sorted(df['month'].unique())
print(f"  {', '.join([str(m) for m in months])}")

print(f"\nCobertura por ticker y mes:")
print(monthly_coverage)

print("\n" + "="*70)
print("✅ CONCLUSIÓN")
print("="*70)
print(f"\n✓ Archivo válido con {len(tickers)} tickers")
print(f"✓ {len(df):,} registros totales")
print(f"✓ Datos desde {df['timestamp'].min().date()} hasta {df['timestamp'].max().date()}")
print(f"✓ Formato: timestamp, OHLCV, ticker")
print(f"✓ Columnas estándar: {df.columns.tolist()}")
