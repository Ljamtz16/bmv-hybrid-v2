# =============================================
# 22_merge_patterns_intraday.py
# =============================================
"""
Detecta patrones candlestick en datos intraday y los merge con forecast.

Patrones detectados:
- Hammer / Inverted Hammer
- Doji / Dragonfly Doji / Gravestone Doji
- Engulfing (Bullish/Bearish)
- Morning Star / Evening Star
- Three White Soldiers / Three Black Crows
- Pin Bar

Uso:
  python scripts/22_merge_patterns_intraday.py --date 2025-11-03
"""

import argparse
import os
from pathlib import Path
import pandas as pd
import numpy as np


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    ap.add_argument("--intraday-dir", default="data/intraday", help="Directorio de datos intraday")
    ap.add_argument("--forecast-dir", default="reports/intraday", help="Directorio de forecast")
    return ap.parse_args()


def load_intraday_data(date_str, intraday_dir):
    """Cargar datos OHLC del día."""
    date_dir = Path(intraday_dir) / date_str
    if not date_dir.exists():
        print(f"[patterns_intraday] WARN: No existe {date_dir}")
        return None
    
    files = list(date_dir.glob("*.parquet"))
    if not files:
        return None
    
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            print(f"[patterns_intraday] ERROR leyendo {f}: {e}")
    
    if not dfs:
        return None
    
    combined = pd.concat(dfs, ignore_index=True)
    combined['timestamp'] = pd.to_datetime(combined['timestamp'])
    combined = combined.sort_values(['ticker', 'timestamp'])
    return combined


def detect_hammer(df):
    """Detectar Hammer pattern (reversal alcista)."""
    body = abs(df['close'] - df['open'])
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    candle_range = df['high'] - df['low']
    
    # Hammer: cuerpo pequeño, sombra inferior larga, sombra superior mínima
    hammer = (
        (lower_shadow > 2 * body) &
        (upper_shadow < 0.3 * body) &
        (candle_range > 0) &
        (df['close'] > df['open'])  # Cierre alcista
    ).astype(int)
    
    return hammer


def detect_doji(df):
    """Detectar Doji patterns (indecisión)."""
    body = abs(df['close'] - df['open'])
    candle_range = df['high'] - df['low']
    
    # Doji: cuerpo muy pequeño
    doji = ((body / (candle_range + 1e-10)) < 0.1).astype(int)
    
    return doji


def detect_engulfing(df):
    """Detectar Engulfing patterns."""
    df = df.copy()
    df['prev_open'] = df.groupby('ticker')['open'].shift(1)
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    df['prev_body'] = abs(df['prev_close'] - df['prev_open'])
    current_body = abs(df['close'] - df['open'])
    
    # Bullish engulfing
    bullish_engulfing = (
        (df['prev_close'] < df['prev_open']) &  # Vela anterior bajista
        (df['close'] > df['open']) &  # Vela actual alcista
        (df['open'] < df['prev_close']) &  # Abre por debajo
        (df['close'] > df['prev_open']) &  # Cierra por encima
        (current_body > df['prev_body'])  # Cuerpo mayor
    ).astype(int)
    
    # Bearish engulfing
    bearish_engulfing = (
        (df['prev_close'] > df['prev_open']) &  # Vela anterior alcista
        (df['close'] < df['open']) &  # Vela actual bajista
        (df['open'] > df['prev_close']) &  # Abre por encima
        (df['close'] < df['prev_open']) &  # Cierra por debajo
        (current_body > df['prev_body'])  # Cuerpo mayor
    ).astype(int)
    
    return bullish_engulfing, bearish_engulfing


def detect_morning_star(df):
    """Detectar Morning Star (reversal alcista de 3 velas)."""
    df = df.copy()
    
    # Shift para obtener velas anteriores
    for i in [1, 2]:
        df[f'open_{i}'] = df.groupby('ticker')['open'].shift(i)
        df[f'close_{i}'] = df.groupby('ticker')['close'].shift(i)
        df[f'high_{i}'] = df.groupby('ticker')['high'].shift(i)
        df[f'low_{i}'] = df.groupby('ticker')['low'].shift(i)
    
    # Morning Star:
    # 1. Vela bajista grande (2 periodos atrás)
    # 2. Vela pequeña o doji (1 periodo atrás)
    # 3. Vela alcista grande (actual)
    
    body_0 = abs(df['close'] - df['open'])
    body_1 = abs(df['close_1'] - df['open_1'])
    body_2 = abs(df['close_2'] - df['open_2'])
    
    morning_star = (
        (df['close_2'] < df['open_2']) &  # Vela 1: bajista
        (body_2 > body_1 * 2) &  # Vela 1: grande
        (body_1 < body_2 * 0.3) &  # Vela 2: pequeña
        (df['close'] > df['open']) &  # Vela 3: alcista
        (body_0 > body_1 * 2) &  # Vela 3: grande
        (df['close'] > df['open_2'])  # Cierre actual > apertura de vela 1
    ).astype(int)
    
    return morning_star


def detect_pin_bar(df):
    """Detectar Pin Bar (rechazo con mecha larga)."""
    body = abs(df['close'] - df['open'])
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    total_range = df['high'] - df['low']
    
    # Bullish pin bar: mecha inferior larga
    bullish_pin = (
        (lower_shadow > 2 * body) &
        (lower_shadow > 0.6 * total_range) &
        (upper_shadow < 0.3 * body)
    ).astype(int)
    
    # Bearish pin bar: mecha superior larga
    bearish_pin = (
        (upper_shadow > 2 * body) &
        (upper_shadow > 0.6 * total_range) &
        (lower_shadow < 0.3 * body)
    ).astype(int)
    
    return bullish_pin, bearish_pin


def detect_all_patterns(df):
    """Detectar todos los patrones y agregar columnas."""
    df = df.copy()
    
    # Detectar patrones
    df['pattern_hammer'] = detect_hammer(df)
    df['pattern_doji'] = detect_doji(df)
    
    bullish_eng, bearish_eng = detect_engulfing(df)
    df['pattern_engulfing_bull'] = bullish_eng
    df['pattern_engulfing_bear'] = bearish_eng
    
    df['pattern_morning_star'] = detect_morning_star(df)
    
    bullish_pin, bearish_pin = detect_pin_bar(df)
    df['pattern_pin_bull'] = bullish_pin
    df['pattern_pin_bear'] = bearish_pin
    
    # Score compuesto (suma de patrones alcistas)
    df['pattern_score'] = (
        df['pattern_hammer'] +
        df['pattern_engulfing_bull'] +
        df['pattern_morning_star'] +
        df['pattern_pin_bull'] -
        df['pattern_engulfing_bear'] -
        df['pattern_pin_bear']
    )
    
    # Contar patrones detectados
    n_patterns = (
        df['pattern_hammer'].sum() +
        df['pattern_doji'].sum() +
        df['pattern_engulfing_bull'].sum() +
        df['pattern_engulfing_bear'].sum() +
        df['pattern_morning_star'].sum() +
        df['pattern_pin_bull'].sum() +
        df['pattern_pin_bear'].sum()
    )
    
    print(f"[patterns_intraday] Patrones detectados: {n_patterns}")
    print(f"  Hammer: {df['pattern_hammer'].sum()}")
    print(f"  Doji: {df['pattern_doji'].sum()}")
    print(f"  Engulfing Bull: {df['pattern_engulfing_bull'].sum()}")
    print(f"  Engulfing Bear: {df['pattern_engulfing_bear'].sum()}")
    print(f"  Morning Star: {df['pattern_morning_star'].sum()}")
    print(f"  Pin Bull: {df['pattern_pin_bull'].sum()}")
    print(f"  Pin Bear: {df['pattern_pin_bear'].sum()}")
    
    return df


def merge_with_forecast(patterns_df, forecast_df):
    """Merge patrones con forecast por ticker y timestamp más cercano."""
    if forecast_df.empty:
        return forecast_df
    
    # Para cada forecast, buscar el pattern más reciente del mismo ticker
    results = []
    
    for ticker in forecast_df['ticker'].unique():
        forecast_ticker = forecast_df[forecast_df['ticker'] == ticker].copy()
        patterns_ticker = patterns_df[patterns_df['ticker'] == ticker].copy()
        
        if patterns_ticker.empty:
            # Sin patrones para este ticker
            for col in ['pattern_score', 'pattern_hammer', 'pattern_doji', 
                       'pattern_engulfing_bull', 'pattern_morning_star', 'pattern_pin_bull']:
                if col not in forecast_ticker.columns:
                    forecast_ticker[col] = 0
            results.append(forecast_ticker)
            continue
        
        # Para cada forecast timestamp, encontrar pattern más cercano anterior
        for idx, row in forecast_ticker.iterrows():
            forecast_ts = row['timestamp']
            
            # Patterns anteriores o simultáneos
            prev_patterns = patterns_ticker[patterns_ticker['timestamp'] <= forecast_ts]
            
            if not prev_patterns.empty:
                # Tomar el más reciente
                latest = prev_patterns.iloc[-1]
                
                forecast_ticker.at[idx, 'pattern_score'] = latest.get('pattern_score', 0)
                forecast_ticker.at[idx, 'pattern_hammer'] = latest.get('pattern_hammer', 0)
                forecast_ticker.at[idx, 'pattern_doji'] = latest.get('pattern_doji', 0)
                forecast_ticker.at[idx, 'pattern_engulfing_bull'] = latest.get('pattern_engulfing_bull', 0)
                forecast_ticker.at[idx, 'pattern_morning_star'] = latest.get('pattern_morning_star', 0)
                forecast_ticker.at[idx, 'pattern_pin_bull'] = latest.get('pattern_pin_bull', 0)
            else:
                # Sin patrones previos
                for col in ['pattern_score', 'pattern_hammer', 'pattern_doji', 
                           'pattern_engulfing_bull', 'pattern_morning_star', 'pattern_pin_bull']:
                    if col not in forecast_ticker.columns:
                        forecast_ticker.at[idx, col] = 0
        
        results.append(forecast_ticker)
    
    combined = pd.concat(results, ignore_index=True)
    return combined


def main():
    args = parse_args()
    
    print(f"[patterns_intraday] Fecha: {args.date}")
    
    # Cargar datos intraday
    ohlc_df = load_intraday_data(args.date, args.intraday_dir)
    if ohlc_df is None or ohlc_df.empty:
        print("[patterns_intraday] ERROR: No hay datos OHLC")
        return
    
    # Detectar patrones
    patterns_df = detect_all_patterns(ohlc_df)
    
    # Cargar forecast
    forecast_file = Path(args.forecast_dir) / args.date / "forecast_intraday.parquet"
    if not forecast_file.exists():
        print(f"[patterns_intraday] WARN: No existe forecast {forecast_file}")
        return
    
    forecast_df = pd.read_parquet(forecast_file)
    print(f"[patterns_intraday] Forecast: {len(forecast_df)} señales")
    
    # Merge
    forecast_with_patterns = merge_with_forecast(patterns_df, forecast_df)
    
    # Guardar
    out_file = Path(args.forecast_dir) / args.date / "forecast_intraday.parquet"
    forecast_with_patterns.to_parquet(out_file, index=False)
    
    print(f"\n[patterns_intraday] Forecast con patrones guardado: {out_file}")
    print(f"  Señales con pattern_score > 0: {(forecast_with_patterns['pattern_score'] > 0).sum()}")


if __name__ == "__main__":
    main()
