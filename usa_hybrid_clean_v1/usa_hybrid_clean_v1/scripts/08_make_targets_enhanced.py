# Script: 08_make_targets_enhanced.py
# Genera targets con dataset enhanced (35 features)
import pandas as pd
import numpy as np
import os

def make_forward_return_target(df, n_days=5, threshold=0.03):
    """Target basado en retorno forward"""
    df['close_fwd'] = df['close'].shift(-n_days)
    df['ret_fwd'] = (df['close_fwd'] - df['close']) / df['close']
    
    df['target'] = np.nan
    df.loc[df['ret_fwd'] > threshold, 'target'] = 1
    df.loc[df['ret_fwd'] < -threshold, 'target'] = 0
    
    return df

def main():
    input_path = 'data/daily/features_daily_enhanced.parquet'
    output_path = 'data/daily/features_enhanced_with_targets.parquet'
    
    if not os.path.exists(input_path):
        print(f"[WARN] No existe {input_path}")
        return
    
    print("[INFO] Cargando features enhanced...")
    df = pd.read_parquet(input_path)
    
    print("[INFO] Generando targets forward...")
    all_targets = []
    for ticker in df['ticker'].unique():
        dft = df[df['ticker'] == ticker].copy()
        dft = make_forward_return_target(dft, n_days=5, threshold=0.03)
        all_targets.append(dft)
    
    df_with_targets = pd.concat(all_targets, ignore_index=True)
    
    # Estadísticas
    total = df_with_targets['target'].notna().sum()
    wins = (df_with_targets['target'] == 1).sum()
    losses = (df_with_targets['target'] == 0).sum()
    
    print(f"\n[OK] Targets generados:")
    print(f"  Total samples: {total:,}")
    print(f"  Wins (1): {wins:,} ({wins/total*100:.1f}%)")
    print(f"  Losses (0): {losses:,} ({losses/total*100:.1f}%)")
    print(f"  Balance: {wins/total:.2f}")
    
    df_with_targets.to_parquet(output_path, index=False, compression='snappy')
    print(f"\n[OK] Guardado en {output_path}")

if __name__ == "__main__":
    main()
