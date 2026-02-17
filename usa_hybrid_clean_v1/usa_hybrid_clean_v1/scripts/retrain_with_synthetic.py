# -*- coding: utf-8 -*-
"""
Reentrenar modelo intraday con datos reales + sintéticos

Combina:
- Features reales (9,585 samples, 2.17% win rate)
- Features sintéticos (2,080 samples, 13% win rate)
-> Dataset balanceado (~5% win rate global)

Uso:
  python scripts/retrain_with_synthetic.py --real features/intraday --synthetic features_synthetic_intraday.parquet --output models_v2
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, classification_report, brier_score_loss
from joblib import dump
import warnings
warnings.filterwarnings('ignore')


def load_real_features(input_dir: Path):
    """Cargar features reales."""
    print(f"[retrain] Cargando features reales...")
    
    dfs = []
    for f in sorted(input_dir.glob("2025-*.parquet")):
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except Exception as e:
            print(f"  WARN: {f.name}: {e}")
    
    df_real = pd.concat(dfs, ignore_index=True)
    print(f"  Real: {len(df_real)} samples")
    
    return df_real


def prepare_combined_dataset(df_real, df_synthetic):
    """Combinar y preparar dataset."""
    print(f"\n[retrain] Combinando datasets...")
    print(f"  Real:      {len(df_real)} samples, win={df_real['win'].mean()*100:.2f}%")
    print(f"  Sintético: {len(df_synthetic)} samples, win={df_synthetic['win'].mean()*100:.2f}%")
    
    # Marcar origen
    df_real['source'] = 'real'
    df_synthetic['source'] = 'synthetic'
    
    # Combinar
    df_combined = pd.concat([df_real, df_synthetic], ignore_index=True)
    
    print(f"  Combinado: {len(df_combined)} samples, win={df_combined['win'].mean()*100:.2f}%")
    
    return df_combined


def train_classifier(df, output_dir: Path):
    """Entrenar clasificador."""
    print(f"\n[retrain] Entrenando clasificador...")
    
    # Features
    feature_cols = [
        'RSI_14', 'MACD', 'MACD_signal', 'BB_upper', 'BB_lower',
        'EMA_9', 'EMA_50', 'ATR_14', 'ATR_pct', 'volume_zscore',
        'VWAP_dev', 'spread_bps', 'turnover_ratio', 'volume_ratio',
        'hour', 'minute', 'dist_to_open', 'dist_to_close',
        'BB_width', 'intraday_pct', 'direction'
    ]
    
    # Filtrar columnas disponibles
    available = [c for c in feature_cols if c in df.columns]
    print(f"  Features disponibles: {len(available)}")
    
    # Preparar datos
    df_train = df[available + ['win']].copy()
    
    # Direction: LONG=1, SHORT=0
    if 'direction' in df_train.columns:
        df_train['direction'] = df_train['direction'].map({'LONG': 1, 'SHORT': 0})
    
    df_train = df_train.dropna()
    
    X = df_train[available].values
    y = df_train['win'].values
    
    print(f"  Samples finales: {len(X)}")
    print(f"  Positivos: {y.sum()} ({y.sum()/len(y)*100:.2f}%)")
    
    # Scaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Modelo
    clf = RandomForestClassifier(
        n_estimators=300,  # Aumentado de 200
        max_depth=12,      # Aumentado de 10
        min_samples_split=10,
        min_samples_leaf=4,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
        verbose=1
    )
    
    print(f"\n  Entrenando RandomForest...")
    clf.fit(X_scaled, y)
    
    # Evaluación
    y_pred_proba = clf.predict_proba(X_scaled)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)
    
    auc = roc_auc_score(y, y_pred_proba)
    brier = brier_score_loss(y, y_pred_proba)
    
    print(f"\n  ROC-AUC:      {auc:.4f}")
    print(f"  Brier Score:  {brier:.4f}")
    
    print(f"\n  Classification Report:")
    print(classification_report(y, y_pred, target_names=['LOSS', 'WIN']))
    
    # Feature importance
    importances = pd.DataFrame({
        'feature': available,
        'importance': clf.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print(f"\n  Top-10 Features:")
    print(importances.head(10).to_string(index=False))
    
    # Guardar
    output_dir.mkdir(parents=True, exist_ok=True)
    dump(clf, output_dir / 'clf_intraday_v2.joblib')
    dump(scaler, output_dir / 'scaler_intraday_v2.joblib')
    
    # Metadata
    metadata = {
        'features': available,
        'n_samples': len(X),
        'n_positives': int(y.sum()),
        'win_rate': float(y.mean()),
        'roc_auc': float(auc),
        'brier_score': float(brier)
    }
    
    import json
    with open(output_dir / 'clf_intraday_v2_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n[retrain] Modelos guardados en {output_dir}/")
    print(f"  - clf_intraday_v2.joblib")
    print(f"  - scaler_intraday_v2.joblib")
    print(f"  - clf_intraday_v2_metadata.json")
    
    return clf, scaler, metadata


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", default="features/intraday", help="Dir features reales")
    ap.add_argument("--synthetic", default="features_synthetic_intraday.parquet", help="Features sintéticos")
    ap.add_argument("--output", default="models", help="Dir output modelos")
    ap.add_argument("--synthetic-weight", type=float, default=1.0, help="Peso sintéticos (1.0=igual)")
    args = ap.parse_args()
    
    real_dir = Path(args.real)
    synthetic_path = Path(args.synthetic)
    output_dir = Path(args.output)
    
    # Cargar
    df_real = load_real_features(real_dir)
    df_synthetic = pd.read_parquet(synthetic_path)
    
    # Aplicar peso sintéticos (undersample si < 1.0, oversample si > 1.0)
    if args.synthetic_weight != 1.0:
        n_synthetic = int(len(df_synthetic) * args.synthetic_weight)
        df_synthetic = df_synthetic.sample(n=n_synthetic, replace=(args.synthetic_weight > 1.0), random_state=42)
        print(f"\n[retrain] Sintéticos resampled: {n_synthetic} (weight={args.synthetic_weight})")
    
    # Combinar
    df_combined = prepare_combined_dataset(df_real, df_synthetic)
    
    # Entrenar
    clf, scaler, metadata = train_classifier(df_combined, output_dir)
    
    print(f"\n{'='*70}")
    print(f"REENTRENAMIENTO COMPLETADO")
    print(f"{'='*70}")
    print(f"Win rate final: {metadata['win_rate']*100:.2f}%")
    print(f"ROC-AUC: {metadata['roc_auc']:.4f}")
    print(f"Samples: {metadata['n_samples']} ({metadata['n_positives']} positivos)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
