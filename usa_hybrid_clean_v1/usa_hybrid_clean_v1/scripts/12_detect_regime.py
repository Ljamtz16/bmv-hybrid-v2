# Script: 12_detect_regime.py
# Clasifica régimen diario (volatilidad, ATR, gap, VIX) y exporta regime_daily.csv
import pandas as pd
import numpy as np
import os

FEATURES_PATH = 'data/daily/features_daily.parquet'
REGIME_PATH = 'data/daily/regime_daily.csv'


def detect_regime(df):
    # Ejemplo: percentiles de ATR y volatilidad
    df['vol_class'] = pd.qcut(df['vol_20d'], q=3, labels=['low_vol','med_vol','high_vol'])
    df['atr_class'] = pd.qcut(df['atr_14d'], q=3, labels=['low_atr','med_atr','high_atr'])
    # Combina en un solo régimen
    df['regime'] = df['vol_class'].astype(str)  # puedes combinar con atr_class si lo deseas
    return df[['timestamp','ticker','regime']]

def main():
    if not os.path.exists(FEATURES_PATH):
        print(f"[WARN] No existe {FEATURES_PATH}")
        return
    df = pd.read_parquet(FEATURES_PATH)
    df_regime = detect_regime(df)
    df_regime.to_csv(REGIME_PATH, index=False)
    print(f"[OK] Regímenes diarios guardados en {REGIME_PATH}")

if __name__ == "__main__":
    main()
