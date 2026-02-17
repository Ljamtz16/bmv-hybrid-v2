"""
Validar fechas de datos - consolidated_15m.parquet vs yfinance
"""
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime

DATA_FILE = Path("C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")

print("="*80)
print("VALIDACION DE FECHAS - DATOS CONSOLIDADOS VS YFINANCE")
print("="*80)

# 1. Check consolidated data
print("\n[1] CONSOLIDATED DATA (consolidated_15m.parquet)")
print("-" * 80)
df_cons = pd.read_parquet(DATA_FILE)
print(f"Ruta: {DATA_FILE}")
print(f"Total rows: {len(df_cons):,}")
print(f"Total tickers: {df_cons['ticker'].nunique()}")

min_date = df_cons['timestamp'].min()
max_date = df_cons['timestamp'].max()
print(f"\nFecha inicial: {min_date}")
print(f"Fecha final:   {max_date}")

# Show distribution by ticker
print(f"\nRows por ticker:")
for ticker in sorted(df_cons['ticker'].unique()):
    count = len(df_cons[df_cons['ticker'] == ticker])
    ticker_dates = df_cons[df_cons['ticker'] == ticker]
    min_t = ticker_dates['timestamp'].min()
    max_t = ticker_dates['timestamp'].max()
    print(f"  {ticker:6} {count:6,} filas | {min_t} a {max_t}")

# 2. Check yfinance availability
print(f"\n[2] YFINANCE - DATOS DISPONIBLES")
print("-" * 80)

sample_tickers = ['SPY', 'AAPL', 'MSFT', 'QQQ', 'NVDA']
print(f"Verificando disponibilidad en yfinance para últimos 15 días...")
print(f"Interval: 15 minutos\n")

for ticker in sample_tickers:
    try:
        df_yf = yf.download(ticker, period="15d", interval="15m", progress=False)
        if not df_yf.empty:
            min_yf = df_yf.index.min()
            max_yf = df_yf.index.max()
            rows_yf = len(df_yf)
            print(f"{ticker:6} | {rows_yf:5,} filas | {min_yf} a {max_yf}")
        else:
            print(f"{ticker:6} | Sin datos")
    except Exception as e:
        print(f"{ticker:6} | Error: {str(e)[:40]}")

# 3. Compare dates
print(f"\n[3] COMPARACION")
print("-" * 80)
cons_max = df_cons['timestamp'].max()
yf_sample = yf.download('SPY', period="15d", interval="15m", progress=False)
yf_max = yf_sample.index.max()

print(f"Consolidated:  {cons_max}")
print(f"YFinance (SPY):{yf_max}")
print(f"\nDiferencia: {yf_max - pd.Timestamp(cons_max)}")

# Check if we have gaps
print(f"\n[4] DETECCIÓN DE GAPS")
print("-" * 80)
df_cons_sorted = df_cons.sort_values('timestamp')
dates = pd.to_datetime(df_cons_sorted['timestamp']).dt.date.unique()
print(f"Fechas únicas en consolidated: {len(dates)}")

# Find gaps
dates_list = sorted(pd.to_datetime(dates))
gaps = []
for i in range(1, len(dates_list)):
    diff_days = (dates_list[i] - dates_list[i-1]).days
    if diff_days > 1:  # Market should be daily except weekends
        gaps.append((dates_list[i-1], dates_list[i], diff_days))

if gaps:
    print(f"\nGaps encontrados:")
    for d1, d2, days in gaps[-5:]:  # Show last 5 gaps
        print(f"  {d1.date()} -> {d2.date()} ({days} días)")
else:
    print("No hay gaps (dentro de lo esperado para fines de semana)")

print(f"\n[5] RESUMEN")
print("-" * 80)
print(f"Fuente de datos consolidados: yfinance descargados y almacenados en parquet")
print(f"Ubicación: {DATA_FILE}")
print(f"Última actualización: {max_date}")
print(f"Estado: {'REQUIERE ACTUALIZACION' if (yf_max - pd.Timestamp(cons_max)).days > 0 else 'ACTUALIZADO'}")
