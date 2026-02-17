import pandas as pd
import os

# Analizar universo de tickers desde features_labeled.csv
print("=" * 70)
print("ANÁLISIS DEL UNIVERSO DE TICKERS")
print("=" * 70)

# Cargar datos
df = pd.read_csv('features_labeled.csv')

# Universo completo
tickers = sorted(df['ticker'].unique())
print(f"\n📊 UNIVERSO COMPLETO: {len(tickers)} tickers\n")
print(", ".join(tickers))

# Top 20 por número de observaciones
print("\n" + "=" * 70)
print("🏆 TOP 20 TICKERS (por número de observaciones)")
print("=" * 70)
df_counts = df['ticker'].value_counts().head(20)
for i, (ticker, count) in enumerate(df_counts.items(), 1):
    print(f"{i:2d}. {ticker:6s}: {count:,} observaciones")

# Estadísticas por ticker
print("\n" + "=" * 70)
print("📈 TOP 20 TICKERS (métricas detalladas)")
print("=" * 70)

top_20_tickers = df_counts.index.tolist()

# Crear tabla resumen
print(f"\n{'Rank':<5} {'Ticker':<8} {'Obs':<10} {'Precio Prom':<13} {'Volatilidad':<12} {'Rango':<25}")
print("-" * 80)

for i, ticker in enumerate(top_20_tickers, 1):
    ticker_data = df[df['ticker'] == ticker]
    
    # Fechas
    fecha_inicio = ticker_data['date'].min()
    fecha_fin = ticker_data['date'].max()
    
    # Estadísticas de precio
    precio_promedio = ticker_data['close'].mean()
    precio_min = ticker_data['close'].min()
    precio_max = ticker_data['close'].max()
    volatilidad = ticker_data['close'].std() / ticker_data['close'].mean() * 100
    
    print(f"{i:<5} {ticker:<8} {len(ticker_data):<10,} ${precio_promedio:<11.2f} {volatilidad:<11.2f}% ${precio_min:.2f} - ${precio_max:.2f}")

# Detalle completo
print("\n" + "=" * 70)
print("📊 DETALLE COMPLETO POR TICKER")
print("=" * 70)

for i, ticker in enumerate(top_20_tickers, 1):
    ticker_data = df[df['ticker'] == ticker]
    
    # Fechas
    fecha_inicio = ticker_data['date'].min()
    fecha_fin = ticker_data['date'].max()
    
    # Estadísticas de precio
    precio_promedio = ticker_data['close'].mean()
    precio_min = ticker_data['close'].min()
    precio_max = ticker_data['close'].max()
    volatilidad = ticker_data['close'].std() / ticker_data['close'].mean() * 100
    
    print(f"\n{i}. {ticker}")
    print(f"   Observaciones: {len(ticker_data):,}")
    print(f"   Período: {fecha_inicio} a {fecha_fin}")
    print(f"   Precio promedio: ${precio_promedio:.2f}")
    print(f"   Rango: ${precio_min:.2f} - ${precio_max:.2f}")
    print(f"   Volatilidad (CV): {volatilidad:.2f}%")

# Información del archivo tickers_master.csv
print("\n" + "=" * 70)
print("📋 UNIVERSO MAESTRO (tickers_master.csv)")
print("=" * 70)
if os.path.exists('data/us/tickers_master.csv'):
    df_master = pd.read_csv('data/us/tickers_master.csv')
    print(f"\nTickers configurados: {len(df_master)}")
    print("\nPor sector:")
    for sector, count in df_master['sector'].value_counts().items():
        tickers_sector = df_master[df_master['sector'] == sector]['ticker'].tolist()
        print(f"  {sector:12s}: {count} tickers - {', '.join(tickers_sector)}")
else:
    print("Archivo no encontrado")

print("\n" + "=" * 70)
