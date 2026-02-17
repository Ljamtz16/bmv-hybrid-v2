# -*- coding: utf-8 -*-
"""
Balanceo de dataset intraday con SMOTE
Genera samples sintéticos WIN para balancear el dataset

Uso:
  python scripts/balance_with_smote.py --input features/intraday --output features_balanced_intraday.parquet --win-rate-target 0.05
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from imblearn.over_sampling import SMOTE, BorderlineSMOTE, ADASYN
import warnings
warnings.filterwarnings('ignore')


def load_features(input_dir: Path):
    """Cargar features reales."""
    print(f"[smote] Cargando features desde {input_dir}...")
    
    dfs = []
    for f in sorted(input_dir.glob("2025-*.parquet")):
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except Exception as e:
            print(f"  WARN: {f.name}: {e}")
    
    df_all = pd.concat(dfs, ignore_index=True)
    print(f"  Cargados: {len(df_all)} samples")
    print(f"  Win rate: {df_all['win'].mean()*100:.2f}%")
    
    return df_all


def prepare_for_smote(df):
    """Preparar features numéricos para SMOTE."""
    print(f"\n[smote] Preparando features...")
    
    # Features numéricos (excluir metadata y target)
    exclude_cols = ['timestamp', 'ticker', 'direction', 'hit_type', 'win', 'tte_bars']
    # Filtrar solo columnas que existen
    exclude_cols = [c for c in exclude_cols if c in df.columns]
    
    numeric_cols = [c for c in df.columns if c not in exclude_cols and df[c].dtype in [np.float64, np.int64, np.float32, np.int32]]
    
    print(f"  Features numéricos: {len(numeric_cols)}")
    
    # Separar features y metadata
    df_features = df[numeric_cols].copy()
    df_metadata = df[exclude_cols].copy()
    
    # Dropna
    valid_idx = df_features.notna().all(axis=1)
    df_features = df_features[valid_idx].copy()
    df_metadata = df_metadata[valid_idx].copy()
    
    print(f"  Samples después de dropna: {len(df_features)}")
    
    return df_features, df_metadata, numeric_cols


def apply_smote(X, y, win_rate_target, method='smote'):
    """Aplicar SMOTE para balancear."""
    print(f"\n[smote] Aplicando {method.upper()}...")
    print(f"  Win rate actual: {y.mean()*100:.2f}%")
    print(f"  Win rate target: {win_rate_target*100:.2f}%")
    
    # Calcular sampling strategy
    n_majority = (y == 0).sum()
    n_minority = (y == 1).sum()
    
    # Target: n_minority_new / (n_majority + n_minority_new) = win_rate_target
    # n_minority_new = win_rate_target * n_majority / (1 - win_rate_target)
    n_minority_target = int(win_rate_target * n_majority / (1 - win_rate_target))
    
    print(f"  Minority actual: {n_minority}")
    print(f"  Minority target: {n_minority_target}")
    print(f"  Samples a generar: {n_minority_target - n_minority}")
    
    if n_minority_target <= n_minority:
        print(f"  WARN: Ya se alcanzó el target, no se aplica SMOTE")
        return X, y
    
    # Seleccionar método
    if method == 'smote':
        sampler = SMOTE(sampling_strategy={1: n_minority_target}, random_state=42, k_neighbors=5)
    elif method == 'borderline':
        sampler = BorderlineSMOTE(sampling_strategy={1: n_minority_target}, random_state=42, k_neighbors=5)
    elif method == 'adasyn':
        sampler = ADASYN(sampling_strategy={1: n_minority_target}, random_state=42, n_neighbors=5)
    else:
        raise ValueError(f"Método {method} no soportado")
    
    X_resampled, y_resampled = sampler.fit_resample(X, y)
    
    print(f"  Samples finales: {len(y_resampled)}")
    print(f"  Win rate final: {y_resampled.mean()*100:.2f}%")
    
    return X_resampled, y_resampled


def reconstruct_dataframe(X_resampled, y_resampled, df_metadata, numeric_cols):
    """Reconstruir DataFrame con samples sintéticos."""
    print(f"\n[smote] Reconstruyendo DataFrame...")
    
    n_original = len(df_metadata)
    n_synthetic = len(X_resampled) - n_original
    
    # Crear DataFrame con features
    df_resampled = pd.DataFrame(X_resampled, columns=numeric_cols)
    df_resampled['win'] = y_resampled
    
    # Metadata para samples originales
    df_meta_full = df_metadata.copy().reset_index(drop=True)
    
    # Metadata para sintéticos (copiar de samples WIN reales)
    if n_synthetic > 0:
        win_samples = df_metadata[df_metadata['win'] == 1]
        
        # Sample con replacement
        df_meta_synthetic = win_samples.sample(n=n_synthetic, replace=True, random_state=42).reset_index(drop=True)
        
        # Marcar como sintético
        df_meta_synthetic['ticker'] = df_meta_synthetic['ticker'] + '_SYN'
        
        # Concatenar metadata
        df_meta_full = pd.concat([df_meta_full, df_meta_synthetic], ignore_index=True)
    
    # Combinar
    df_final = pd.concat([df_meta_full.reset_index(drop=True), df_resampled], axis=1)
    
    print(f"  Samples originales: {n_original}")
    print(f"  Samples sintéticos: {n_synthetic}")
    print(f"  Total: {len(df_final)}")
    
    return df_final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="features/intraday", help="Dir features")
    ap.add_argument("--output", default="features_balanced_intraday.parquet", help="Output parquet")
    ap.add_argument("--win-rate-target", type=float, default=0.05, help="Win rate objetivo (5% default)")
    ap.add_argument("--method", choices=['smote', 'borderline', 'adasyn'], default='smote', help="Método SMOTE")
    args = ap.parse_args()
    
    input_dir = Path(args.input)
    output_path = Path(args.output)
    
    # 1. Cargar
    df = load_features(input_dir)
    
    # 2. Preparar
    df_features, df_metadata, numeric_cols = prepare_for_smote(df)
    
    X = df_features.values
    y = df_metadata['win'].values
    
    # 3. SMOTE
    X_resampled, y_resampled = apply_smote(X, y, args.win_rate_target, args.method)
    
    # 4. Reconstruir
    df_balanced = reconstruct_dataframe(X_resampled, y_resampled, df_metadata, numeric_cols)
    
    # 5. Guardar
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_balanced.to_parquet(output_path, index=False)
    
    print(f"\n[smote] Dataset balanceado guardado: {output_path}")
    print(f"  Shape: {df_balanced.shape}")
    print(f"  Win rate: {df_balanced['win'].mean()*100:.2f}%")
    print(f"  Tickers: {df_balanced['ticker'].nunique()}")
    
    # Stats por origen
    n_synthetic = (df_balanced['ticker'].str.contains('_SYN')).sum()
    print(f"\n[smote] Composición:")
    print(f"  Reales:     {len(df_balanced) - n_synthetic}")
    print(f"  Sintéticos: {n_synthetic}")


if __name__ == "__main__":
    main()
