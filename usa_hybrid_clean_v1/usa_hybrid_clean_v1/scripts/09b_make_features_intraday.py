# Script: 09b_make_features_intraday.py
# Genera features de contexto intradía agregados al día
import pandas as pd
import numpy as np
import os
import glob

def compute_intraday_features(df):
    # Volatilidad intradía
    df['vol_30m'] = df['close'].rolling(6).std()  # 6*5m=30m
    df['vol_60m'] = df['close'].rolling(12).std()
    # ATR intradía
    df['tr'] = np.maximum(df['high']-df['low'], np.abs(df['high']-df['close'].shift()), np.abs(df['low']-df['close'].shift()))
    df['atr_5m'] = df['tr'].rolling(3).mean()
    df['atr_15m'] = df['tr'].rolling(9).mean()
    # EMA cross
    df['ema_8'] = df['close'].ewm(span=8).mean()
    df['ema_21'] = df['close'].ewm(span=21).mean()
    df['ema_cross'] = (df['ema_8'] > df['ema_21']).astype(int)
    # Ratio de colas
    df['upper_tail'] = df['high'] - df[['open','close']].max(axis=1)
    df['lower_tail'] = df[['open','close']].min(axis=1) - df['low']
    df['tail_ratio'] = df['upper_tail'] / (df['lower_tail'] + 1e-6)
    # Breakouts
    df['hh_20'] = (df['high'] >= df['high'].rolling(20).max()).astype(int)
    df['ll_20'] = (df['low'] <= df['low'].rolling(20).min()).astype(int)
    return df

def main():
    input_dir = 'data/intraday5/history/'
    output_path = 'data/intraday5/features_intraday.parquet'
    all_feat = []
    for ticker_dir in glob.glob(f"{input_dir}ticker=*/"):
        ticker = ticker_dir.split('=')[1].replace('/', '')
        for date_dir in glob.glob(f"{ticker_dir}date=*/"):
            for f in glob.glob(f"{date_dir}*.parquet"):
                df = pd.read_parquet(f)
                if df.empty:
                    continue
                df = compute_intraday_features(df)
                # Agregar resumen diario (ejemplo: media, std, último valor)
                summary = df.iloc[-1:].copy()
                summary['ticker'] = ticker
                summary['date'] = df['timestamp'].dt.date.iloc[-1]
                all_feat.append(summary)
    if all_feat:
        df_feat = pd.concat(all_feat)
        df_feat.to_parquet(output_path, index=False, compression='snappy')
        print(f"[OK] Features intradía guardados en {output_path}")
    else:
        print("[WARN] No se generaron features intradía.")

if __name__ == "__main__":
    main()
