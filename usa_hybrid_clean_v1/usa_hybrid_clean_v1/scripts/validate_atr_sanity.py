import pandas as pd
import numpy as np
import os

FEATURES_PATH = 'data/daily/features_enhanced_adaptive_targets.parquet'

def main():
    if not os.path.exists(FEATURES_PATH):
        print(f"[WARN] No existe {FEATURES_PATH}")
        return

    df = pd.read_parquet(FEATURES_PATH)
    req = {'atr_pct_w','thr_up','thr_dn','target_binary','target_ordinal'}
    missing = req - set(df.columns)
    if missing:
        print(f"[WARN] Faltan columnas: {missing}")
    
    print("="*60)
    print("ATR% & Thresholds - Sanity Check")
    print("="*60)
    
    atr_med = df['atr_pct_w'].median()*100 if 'atr_pct_w' in df else np.nan
    print(f"ATR%% Mediana: {atr_med:.2f}% (esperado ~1-3%)")
    if 'thr_up' in df:
        print(f"thr_up Mediana: {df['thr_up'].median()*100:.2f}%")
    if 'thr_dn' in df:
        print(f"thr_dn Mediana: {df['thr_dn'].median()*100:.2f}%")

    if 'target_binary' in df:
        bin_valid = df['target_binary'].notna().sum()
        bin_pos = (df['target_binary']==1).sum()
        bin_neg = (df['target_binary']==0).sum()
        if bin_valid>0:
            print("\nTarget BINARIO:")
            print(f"  Samples: {bin_valid:,}")
            print(f"  1s: {bin_pos:,} ({bin_pos/bin_valid*100:.1f}%)")
            print(f"  0s: {bin_neg:,} ({bin_neg/bin_valid*100:.1f}%)")
    
    if 'target_ordinal' in df:
        ord_valid = df['target_ordinal'].notna().sum()
        if ord_valid>0:
            print("\nTarget ORDINAL:")
            print(df['target_ordinal'].value_counts().sort_index().to_string())

if __name__ == '__main__':
    main()
