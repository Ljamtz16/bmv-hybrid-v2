# Script 00 — Build Daily Bars
# Deriva OHLC diario por (ticker, date) desde datos 15m sin loops
#
# Input:  consolidated_15m.parquet (ticker, datetime/timestamp, open, high, low, close)
# Output: artifacts/daily_bars.parquet (ticker, date, open, high, low, close)

import pandas as pd
import numpy as np
from pathlib import Path

def build_daily_bars(input_path: str, output_path: str) -> pd.DataFrame:
    """
    Construye barras diarias desde datos intradía 15m.
    
    Returns:
        DataFrame con columnas: ticker, date, open, high, low, close
    """
    print(f"[00] Leyendo datos desde {input_path}...")
    df = pd.read_parquet(input_path)
    
    print(f"[00] Filas cargadas: {len(df):,}")
    print(f"[00] Columnas disponibles: {df.columns.tolist()}")
    
    # Normalizar nombre de columna datetime/timestamp
    if 'timestamp' in df.columns and 'datetime' not in df.columns:
        df = df.rename(columns={'timestamp': 'datetime'})
    
    # Validar columnas requeridas
    required_cols = ['ticker', 'datetime', 'open', 'high', 'low', 'close']
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")
    
    # Convertir datetime a datetime64
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # Crear date normalizado (00:00)
    df['date'] = df['datetime'].dt.floor('D')
    
    print(f"[00] Rango de fechas: {df['date'].min()} → {df['date'].max()}")
    print(f"[00] Tickers únicos: {df['ticker'].nunique()}")
    
    # Ordenar por ticker y datetime (crítico para first/last)
    df = df.sort_values(['ticker', 'datetime'])
    
    # Agregación vectorizada por (ticker, date)
    print(f"[00] Agregando a diario...")
    daily = df.groupby(['ticker', 'date'], as_index=False).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    })
    
    # Validaciones
    print(f"\n[00] === VALIDACIONES ===")
    
    # 1. No duplicados
    duplicates = daily.duplicated(subset=['ticker', 'date']).sum()
    print(f"[00] Duplicados (ticker, date): {duplicates}")
    if duplicates > 0:
        raise ValueError(f"Se encontraron {duplicates} duplicados en (ticker, date)")
    
    # 2. No NaN masivos
    nan_pct = daily[['open', 'high', 'low', 'close']].isna().sum() / len(daily) * 100
    print(f"[00] % NaN por columna:\n{nan_pct}")
    if nan_pct.max() > 5:
        print(f"[00] ⚠️  ADVERTENCIA: >5% NaN en alguna columna OHLC")
    
    # 3. Validación OHLC lógica
    invalid_ohlc = (
        (daily['high'] < daily['low']) |
        (daily['high'] < daily['open']) |
        (daily['high'] < daily['close']) |
        (daily['low'] > daily['open']) |
        (daily['low'] > daily['close'])
    ).sum()
    print(f"[00] Filas con OHLC inválido: {invalid_ohlc}")
    if invalid_ohlc > 0:
        print(f"[00] ⚠️  {invalid_ohlc} filas con lógica OHLC inconsistente")
    
    # 4. Estadísticas finales
    print(f"\n[00] === RESULTADO ===")
    print(f"[00] Filas diarias generadas: {len(daily):,}")
    print(f"[00] Esperado aprox: {daily['ticker'].nunique()} tickers × {daily['date'].nunique()} días = {daily['ticker'].nunique() * daily['date'].nunique():,}")
    print(f"[00] Cobertura: {len(daily) / (daily['ticker'].nunique() * daily['date'].nunique()) * 100:.1f}%")
    
    # Guardar
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    daily.to_parquet(output_path, index=False)
    print(f"\n[00] ✅ Guardado en: {output_path}")
    print(f"[00] Tamaño: {Path(output_path).stat().st_size / 1024 / 1024:.2f} MB")
    
    return daily


if __name__ == '__main__':
    # Paths
    INPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet'
    OUTPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\daily_bars.parquet'
    
    # Ejecutar
    daily_bars = build_daily_bars(INPUT_FILE, OUTPUT_FILE)
    
    # Muestra
    print(f"\n[00] === MUESTRA ===")
    print(daily_bars.head(10))
    print(f"\n[00] Sample para validación manual:")
    sample = daily_bars.sample(min(3, len(daily_bars)))
    print(sample[['ticker', 'date', 'open', 'high', 'low', 'close']])