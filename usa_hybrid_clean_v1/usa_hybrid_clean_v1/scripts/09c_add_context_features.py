# Script: 09c_add_context_features.py
# Agrega 10 features de contexto para mejorar poder predictivo
import pandas as pd
import numpy as np
import os

def add_context_features(df):
    """
    Agrega features de contexto:
    - %gap apertura
    - Distancia a HH/LL (20/60 días)
    - Rango verdadero normalizado
    - Día de semana (one-hot)
    - Posición en mes
    """
    df = df.sort_values(['ticker', 'timestamp']).copy()
    
    # 1. Gap de apertura
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    df['gap_pct'] = (df['open'] - df['prev_close']) / df['prev_close']
    
    # 2. Distancia a HH/LL
    df['hh_20'] = df.groupby('ticker')['high'].transform(lambda x: x.rolling(20).max())
    df['ll_20'] = df.groupby('ticker')['low'].transform(lambda x: x.rolling(20).min())
    df['hh_60'] = df.groupby('ticker')['high'].transform(lambda x: x.rolling(60).max())
    df['ll_60'] = df.groupby('ticker')['low'].transform(lambda x: x.rolling(60).min())
    
    df['dist_to_hh_20'] = (df['close'] - df['hh_20']) / df['hh_20']
    df['dist_to_ll_20'] = (df['close'] - df['ll_20']) / df['ll_20']
    df['dist_to_hh_60'] = (df['close'] - df['hh_60']) / df['hh_60']
    df['dist_to_ll_60'] = (df['close'] - df['ll_60']) / df['ll_60']
    
    # 3. Rango verdadero normalizado (True Range / Close)
    df['tr_norm'] = df['tr'] / df['close']
    
    # 4. Day of week (Monday=0, Friday=4)
    df['dow'] = pd.to_datetime(df['timestamp']).dt.dayofweek
    
    # One-hot encoding for day of week
    for dow in range(5):  # 0-4 (Mon-Fri)
        df[f'dow_{dow}'] = (df['dow'] == dow).astype(int)
    
    # 5. Posición en mes (0-1, donde 0=inicio, 1=fin)
    df['day_of_month'] = pd.to_datetime(df['timestamp']).dt.day
    df['pos_in_month'] = (df['day_of_month'] - 1) / 30  # Aprox
    
    # 6. Volumen relativo (vs promedio 20d)
    df['vol_avg_20'] = df.groupby('ticker')['volume'].transform(lambda x: x.rolling(20).mean())
    df['vol_rel'] = df['volume'] / df['vol_avg_20']
    
    # 7. Momentum de corto plazo (ret_2d, ret_3d)
    df['ret_2d'] = df.groupby('ticker')['close'].pct_change(2)
    df['ret_3d'] = df.groupby('ticker')['close'].pct_change(3)
    
    # 8. Volatility ratio (vol_5d / vol_20d)
    df['vol_ratio'] = df['vol_5d'] / df['vol_20d']
    
    # 9. Price momentum strength (ret_5d / vol_5d)
    df['momentum_strength'] = df['ret_5d'] / (df['vol_5d'] + 1e-6)
    
    # 10. Consecutive up/down days
    df['is_up'] = (df['close'] > df['prev_close']).astype(int)
    df['consec_up'] = df.groupby('ticker')['is_up'].transform(
        lambda x: x.groupby((x != x.shift()).cumsum()).cumsum()
    )
    
    return df

def main():
    input_path = 'data/daily/features_daily.parquet'
    output_path = 'data/daily/features_daily_enhanced.parquet'
    
    if not os.path.exists(input_path):
        print(f"[WARN] No existe {input_path}")
        return
    
    print("[INFO] Cargando features básicas...")
    df = pd.read_parquet(input_path)
    
    print("[INFO] Agregando features de contexto...")
    df = add_context_features(df)
    
    # Listar features agregadas
    new_features = [
        'gap_pct', 'dist_to_hh_20', 'dist_to_ll_20', 'dist_to_hh_60', 'dist_to_ll_60',
        'tr_norm', 'dow_0', 'dow_1', 'dow_2', 'dow_3', 'dow_4', 'pos_in_month',
        'vol_rel', 'ret_2d', 'ret_3d', 'vol_ratio', 'momentum_strength', 'consec_up'
    ]
    
    print(f"\n[OK] Features agregadas ({len(new_features)}):")
    for feat in new_features:
        non_null = df[feat].notna().sum()
        print(f"  - {feat:20s}: {non_null:,} non-null")
    
    # Contar features totales
    feature_cols = [c for c in df.columns if c not in ['timestamp', 'ticker', 'open', 'high', 'low', 'close', 'volume']]
    print(f"\n[INFO] Features totales: {len(feature_cols)}")
    
    df.to_parquet(output_path, index=False, compression='snappy')
    print(f"\n[OK] Guardado en {output_path}")
    print(f"[INFO] Shape: {df.shape}")

if __name__ == "__main__":
    main()
