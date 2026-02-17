#!/usr/bin/env python3
"""
Descargar datos intraday 15m para todos los tickers del universo completo
Basado en la mejor configuración encontrada (paper_dec_2025_ab_new)
"""

import subprocess
import sys
from datetime import datetime

# Universo completo de 18 tickers (ver tickers_master.csv)
ALL_TICKERS = [
    'AAPL', 'AMD', 'AMZN', 'CAT', 'CVX', 'GS', 'IWM', 'JNJ', 
    'JPM', 'MS', 'MSFT', 'NVDA', 'PFE', 'QQQ', 'SPY', 'TSLA', 
    'WMT', 'XOM'
]

# Configuración
MONTH = "2025-12"  # Mes a descargar
INTERVAL = "15m"

def download_week(tickers, start, end, week_num, month):
    """Descarga datos de una semana para los tickers especificados."""
    output_file = f"data/intraday_15m/{month}_w{week_num}_ALL.parquet"
    
    tickers_str = " ".join(tickers)
    cmd = [
        "python", "paper/intraday_data.py",
        "--tickers", *tickers,
        "--start", start,
        "--end", end,
        "--interval", INTERVAL,
        "--out", output_file
    ]
    
    print(f"\n{'='*70}")
    print(f"📥 Descargando Semana {week_num}: {start} a {end}")
    print(f"   Tickers: {', '.join(tickers)}")
    print(f"   Output: {output_file}")
    print(f"{'='*70}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Semana {week_num} completada")
        return output_file
    else:
        print(f"❌ Error en semana {week_num}")
        print(result.stderr)
        return None

def main():
    print("="*70)
    print("🚀 DESCARGA DE DATOS INTRADAY 15M - UNIVERSO COMPLETO")
    print("="*70)
    print(f"\n📊 Tickers a descargar: {len(ALL_TICKERS)}")
    print(f"   {', '.join(ALL_TICKERS)}")
    print(f"\n📅 Mes: {MONTH}")
    print(f"⏱️  Intervalo: {INTERVAL}")
    
    # Diciembre 2025 - 4 semanas
    weeks = [
        ("2025-12-01", "2025-12-07", 1),
        ("2025-12-08", "2025-12-14", 2),
        ("2025-12-15", "2025-12-21", 3),
        ("2025-12-22", "2025-12-31", 4),
    ]
    
    print(f"\n📦 Total semanas: {len(weeks)}")
    
    # Confirmar
    response = input("\n¿Continuar con la descarga? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelado")
        sys.exit(0)
    
    # Descargar por semanas
    output_files = []
    for start, end, week_num in weeks:
        result = download_week(ALL_TICKERS, start, end, week_num, MONTH)
        if result:
            output_files.append(result)
        else:
            print(f"\n⚠️  Falló semana {week_num}, continuando...")
    
    print("\n" + "="*70)
    print("📋 RESUMEN DE DESCARGA")
    print("="*70)
    print(f"✅ Archivos creados: {len(output_files)}/{len(weeks)}")
    
    if output_files:
        print("\n📁 Archivos generados:")
        for f in output_files:
            print(f"   - {f}")
        
        print("\n" + "="*70)
        print("📌 SIGUIENTE PASO: MERGE")
        print("="*70)
        print("\nEjecuta este comando para combinar todas las semanas:")
        print(f'\npython paper/merge_intraday_parquets.py \\')
        print(f'  --input-pattern "data/intraday_15m/{MONTH}_w*_ALL.parquet" \\')
        print(f'  --out "data/intraday_15m/{MONTH}_ALL_TICKERS.parquet" \\')
        print(f'  --verbose')
    else:
        print("\n❌ No se generaron archivos")

if __name__ == "__main__":
    main()
