# Script: 09_make_features_daily.py
# Genera features diarios avanzados para cada ticker
import pandas as pd
import numpy as np
import os

def compute_daily_features(df):
    # Momentum multi-ventana
    df['ret_1d'] = df['close'].pct_change(1)
    df['ret_5d'] = df['close'].pct_change(5)
    df['ret_20d'] = df['close'].pct_change(20)
    # Volatilidad
    df['vol_5d'] = df['close'].rolling(5).std()
    df['vol_20d'] = df['close'].rolling(20).std()
    # ATR
    df['tr'] = np.maximum(df['high']-df['low'], np.abs(df['high']-df['close'].shift()), np.abs(df['low']-df['close'].shift()))
    df['atr_14d'] = df['tr'].rolling(14).mean()
    # Position in range
    df['pos_in_range_20d'] = (df['close'] - df['low'].rolling(20).min()) / (df['high'].rolling(20).max() - df['low'].rolling(20).min())
    # TODO: patrones, sector, distancia a earnings
    return df

def main():
    input_path = 'data/daily/ohlcv_daily.parquet'
    output_path = 'data/daily/features_daily.parquet'
    if not os.path.exists(input_path):
        print(f"[WARN] No existe {input_path}")
        return
    
    print("[INFO] Cargando datos diarios...")
    df_any = pd.read_parquet(input_path)
    
    # Ruta A: Si ya viene en long (ticker presente), normalizar y seguir
    if 'ticker' in df_any.columns and {'open','high','low','close','volume'}.issubset(df_any.columns):
        print("[INFO] Detectado formato long. Normalizando...")
        df = df_any.copy()
        # Asegurar timestamp
        if 'timestamp' not in df.columns:
            if 'date' in df.columns:
                df['timestamp'] = pd.to_datetime(df['date'], utc=True, errors='coerce')
            else:
                raise SystemExit("Dataset long sin 'date' ni 'timestamp'")
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
        df = df.dropna(subset=['close'])
        print(f"[OK] Long: {len(df)} filas, {df['ticker'].nunique()} tickers")
    else:
        # Ruta B: Convertir de formato wide (MultiIndex columns) a formato long
        print("[INFO] Convirtiendo de formato wide a long...")
        df_wide = df_any
        df_wide.columns = pd.MultiIndex.from_tuples(
            [eval(c) if isinstance(c, str) and c.startswith("(") else (c, '') for c in df_wide.columns]
        )
        records = []
        timestamp_col = df_wide[('timestamp', '')]
        for ticker in [c[1] for c in df_wide.columns if c[1] and c[0] == 'open']:
            ticker_df = pd.DataFrame({
                'timestamp': timestamp_col,
                'open': df_wide[('open', ticker)],
                'high': df_wide[('high', ticker)],
                'low': df_wide[('low', ticker)],
                'close': df_wide[('close', ticker)],
                'volume': df_wide[('volume', ticker)],
                'ticker': ticker
            })
            records.append(ticker_df)
        df = pd.concat(records, ignore_index=True).dropna(subset=['close'])
        print(f"[OK] Formato long: {len(df)} filas, {df['ticker'].nunique()} tickers")
    
    features = []
    for ticker in df['ticker'].unique():
        dft = df[df['ticker'] == ticker].copy()
        dft = compute_daily_features(dft)
        features.append(dft)
    df_feat = pd.concat(features)
    df_feat.to_parquet(output_path, index=False, compression='snappy')
    print(f"[OK] Features diarios guardados en {output_path}")

if __name__ == "__main__":
    main()
