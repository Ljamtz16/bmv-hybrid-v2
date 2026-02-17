# Script 02 — Build Regime Table
# Construye contexto macro intraday self-contained por (ticker, date)
# con ATR, EMA, flags de régimen y side derivado
#
# Input:  artifacts/daily_bars.parquet
# Output: artifacts/regime_table.parquet

import pandas as pd
import numpy as np
from pathlib import Path

def build_regime_table(
    input_path: str,
    output_path: str,
    atr_period: int = 14,
    ema_period: int = 20,
    wide_range_pctl: float = 0.75,  # percentil por ticker
    directional_k: float = 0.50  # unidades de ATR (aumentado para ser más estricto)
) -> pd.DataFrame:
    """
    Construye tabla de régimen con indicadores técnicos y flags.
    
    Returns:
        DataFrame con: ticker, date, OHLC, tr, atr14, ema20, 
                       daily_range_pct, atr_p75, is_high_vol, 
                       is_wide_range, is_directional, side
    """
    print(f"[02] Leyendo daily bars desde {input_path}...")
    df = pd.read_parquet(input_path)
    
    print(f"[02] Filas cargadas: {len(df):,}")
    print(f"[02] Tickers: {df['ticker'].nunique()}")
    print(f"[02] Rango: {df['date'].min()} → {df['date'].max()}")
    
    # Ordenar por ticker y fecha (crítico para rolling/shift)
    df = df.sort_values(['ticker', 'date'])
    
    # === A) TRUE RANGE (TR) ===
    print(f"\n[02] Calculando True Range...")
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    
    df['tr'] = np.maximum.reduce([
        df['high'] - df['low'],
        np.abs(df['high'] - df['prev_close']),
        np.abs(df['low'] - df['prev_close'])
    ])
    
    # Primera fila por ticker: TR = high - low
    df['tr'] = df['tr'].fillna(df['high'] - df['low'])
    
    # === B) ATR14 ===
    print(f"[02] Calculando ATR{atr_period}...")
    df['atr14'] = (
        df.groupby('ticker')['tr']
        .transform(lambda x: x.rolling(atr_period, min_periods=1).mean())
    )
    
    # === C) EMA20 ===
    print(f"[02] Calculando EMA{ema_period}...")
    df['ema20'] = (
        df.groupby('ticker')['close']
        .transform(lambda x: x.ewm(span=ema_period, adjust=False).mean())
    )
    
    # === D) DAILY_RANGE_PCT ===
    print(f"[02] Calculando daily_range_pct...")
    df['daily_range_pct'] = (df['high'] - df['low']) / df['open']
    
    # === E) FLAGS ===
    print(f"\n[02] Construyendo flags de régimen...")
    
    # E.1) ATR percentil 75 por ticker
    df['atr_p75'] = (
        df.groupby('ticker')['atr14']
        .transform(lambda x: x.quantile(0.75))
    )
    
    # E.2) is_high_vol
    df['is_high_vol'] = df['atr14'] > df['atr_p75']
    
    # E.3) is_wide_range (adaptativo por ticker, usando percentil)
    wide_p75 = df.groupby('ticker')['daily_range_pct'].quantile(wide_range_pctl)
    df['wide_thr'] = df['ticker'].map(wide_p75)
    df['is_wide_range'] = df['daily_range_pct'] > df['wide_thr']
    
    # E.4) is_directional (distancia a EMA en unidades de ATR)
    df['ema_dist'] = (df['close'] - df['ema20']).abs()
    df['is_directional'] = df['ema_dist'] > (directional_k * df['atr14'])
    
    # E.5) side derivado
    df['side'] = np.where(df['close'] > df['ema20'], 'BUY', 'SELL')
    
    # === F) PREV FEATURES (ANTI-LEAKAGE) ===
    print(f"[02] Calculando versiones previas (shift) para anti-leakage...")
    df['ema20_prev'] = df.groupby('ticker')['ema20'].shift(1)
    df['atr14_prev'] = df.groupby('ticker')['atr14'].shift(1)
    df['daily_range_pct_prev'] = df.groupby('ticker')['daily_range_pct'].shift(1)
    df['is_high_vol_prev'] = df.groupby('ticker')['is_high_vol'].shift(1)
    df['is_wide_range_prev'] = df.groupby('ticker')['is_wide_range'].shift(1)
    df['is_directional_prev'] = df.groupby('ticker')['is_directional'].shift(1)
    
    # side prev: usa close del día anterior vs ema20_prev
    prev_close = df.groupby('ticker')['close'].shift(1)
    df['side_prev'] = np.where(prev_close > df['ema20_prev'], 'BUY', 'SELL')
    
    # Limpieza de columnas auxiliares
    df = df.drop(columns=['prev_close', 'wide_thr', 'ema_dist'], errors='ignore')
    
    # === VALIDACIONES ===
    print(f"\n[02] === VALIDACIONES ===")
    
    # Filtrar filas con suficiente historia (mínimo para ATR/EMA)
    valid_rows = df['atr14'].notna() & df['ema20'].notna()
    n_valid = valid_rows.sum()
    n_total = len(df)
    
    print(f"[02] Filas con indicadores completos: {n_valid:,} / {n_total:,} ({n_valid/n_total*100:.1f}%)")
    
    # Proporciones de flags (sobre filas válidas)
    df_valid = df[valid_rows].copy()
    
    pct_high_vol = df_valid['is_high_vol'].mean() * 100
    pct_wide_range = df_valid['is_wide_range'].mean() * 100
    pct_directional = df_valid['is_directional'].mean() * 100
    
    print(f"\n[02] Proporciones de flags (sobre filas válidas):")
    print(f"[02]   is_high_vol:     {pct_high_vol:.1f}%")
    print(f"[02]   is_wide_range:   {pct_wide_range:.1f}%")
    print(f"[02]   is_directional:  {pct_directional:.1f}%")
    
    print(f"\n[02] Parámetros adaptativos usados:")
    print(f"[02]   wide_range_pctl: {wide_range_pctl:.2%} (percentil por ticker)")
    print(f"[02]   directional_k: {directional_k:.2f}x ATR14")
    
    # Advertencias
    if pct_high_vol < 15 or pct_high_vol > 40:
        print(f"[02] ⚠️  is_high_vol fuera de rango esperado (20-35%)")
    
    if pct_wide_range < 15 or pct_wide_range > 50:
        print(f"[02] ⚠️  is_wide_range fuera de rango esperado (20-45%)")
    
    if pct_directional < 30 or pct_directional > 80:
        print(f"[02] ⚠️  is_directional fuera de rango esperado (40-70%)")
    
    # Distribución de side
    side_dist = df_valid['side'].value_counts(normalize=True) * 100
    print(f"\n[02] Distribución de side:")
    print(side_dist)
    
    # Triple flag (días operables ideales)
    triple_flag = (
        df_valid['is_high_vol'] & 
        df_valid['is_wide_range'] & 
        df_valid['is_directional']
    ).mean() * 100
    print(f"\n[02] Días con triple flag (operables ideales): {triple_flag:.1f}%")
    
    # === GUARDAR ===
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df.to_parquet(output_path, index=False)
    print(f"\n[02] ✅ Guardado en: {output_path}")
    print(f"[02] Tamaño: {Path(output_path).stat().st_size / 1024 / 1024:.2f} MB")
    print(f"[02] Columnas: {df.columns.tolist()}")
    
    return df


if __name__ == '__main__':
    # Paths
    INPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\daily_bars.parquet'
    OUTPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\regime_table.parquet'
    
    # Ejecutar
    regime = build_regime_table(INPUT_FILE, OUTPUT_FILE)
    
    # Muestra
    print(f"\n[02] === MUESTRA ===")
    cols_display = ['ticker', 'date', 'close', 'atr14', 'ema20', 
                    'is_high_vol', 'is_wide_range', 'is_directional', 'side']
    print(regime[cols_display].head(20))
    
    # Sample de días operables
    print(f"\n[02] Días con triple flag (sample):")
    triple = regime[
        regime['is_high_vol'] & 
        regime['is_wide_range'] & 
        regime['is_directional']
    ]
    if len(triple) > 0:
        print(triple[cols_display].head(10))
    else:
        print("[02] No hay días con triple flag en este dataset")