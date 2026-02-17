# =============================================
# 10_train_intraday.py
# =============================================
"""
Entrena clasificador de prob_win para intraday.

Modelo: RandomForest o XGBoost
Target: win (1 si TP antes que SL)
Rolling window: 60-90 días

Uso:
  python scripts/10_train_intraday.py --start 2025-09-01 --end 2025-10-31 --interval 15m
  python scripts/10_train_intraday.py --start 2025-09-01 --end 2025-10-31 --model xgb
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, roc_auc_score, brier_score_loss
import yaml

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="Fecha inicio YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="Fecha fin YYYY-MM-DD")
    ap.add_argument("--features-dir", default="features/intraday", help="Directorio de features")
    ap.add_argument("--model-type", default="rf", choices=["rf", "xgb"], help="Tipo de modelo")
    ap.add_argument("--out-model", default="models/clf_intraday.joblib", help="Modelo de salida")
    ap.add_argument("--out-scaler", default="models/scaler_intraday.joblib", help="Scaler de salida")
    ap.add_argument("--config", default="config/intraday.yaml", help="Archivo de configuración")
    ap.add_argument("--min-samples", type=int, default=1000, help="Mínimo de muestras para entrenar")
    return ap.parse_args()


def load_config(config_path):
    """Cargar configuración."""
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def get_date_range(start_str, end_str):
    """Obtener lista de fechas."""
    start = datetime.fromisoformat(start_str)
    end = datetime.fromisoformat(end_str)
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def load_training_data(dates, features_dir):
    """Cargar datos de features para fechas especificadas."""
    dfs = []
    for date in dates:
        file_path = Path(features_dir) / f"{date}.parquet"
        if file_path.exists():
            try:
                df = pd.read_parquet(file_path)
                if not df.empty:
                    dfs.append(df)
            except Exception as e:
                print(f"[train_intraday] ERROR leyendo {file_path}: {e}")
    
    if not dfs:
        return None
    
    combined = pd.concat(dfs, ignore_index=True)
    print(f"[train_intraday] Cargadas {len(combined)} filas de {len(dfs)} archivos")
    return combined


def get_feature_columns(config):
    """Obtener lista de columnas de features."""
    # Features técnicos básicos
    features = [
        'RSI_7', 'RSI_14',
        'EMA_9', 'EMA_20', 'EMA_50',
        'MACD', 'MACD_signal', 'MACD_hist',
        'ATR_14', 'ATR_pct',
        'BB_width',
        'volume_ratio', 'volume_zscore',
        'VWAP_dev',
        'spread_bps', 'turnover_ratio',
        'dist_to_open', 'dist_to_close',
        'is_first_hour', 'is_last_hour',
        'direction'  # <-- NUEVO: Incluir dirección (LONG=1, SHORT=0)
    ]
    
    # Agregar features de config si existen
    config_features = config.get('features', {})
    if 'technical' in config_features:
        for feat in config_features['technical']:
            if feat not in features:
                features.append(feat)
    
    return features


def prepare_train_data(df, feature_cols):
    """Preparar datos de entrenamiento."""
    # Filtrar filas completas
    required_cols = feature_cols + ['win']
    df_clean = df[required_cols].copy()
    
    # Convertir direction de categórico a numérico: LONG=1, SHORT=0
    if 'direction' in df_clean.columns:
        df_clean['direction'] = (df_clean['direction'] == 'LONG').astype(int)
    
    df_clean = df_clean.dropna()
    
    if df_clean.empty:
        return None, None
    
    X = df_clean[feature_cols].values
    y = df_clean['win'].values
    
    return X, y


def train_model(X, y, model_type='rf'):
    """Entrenar modelo."""
    print(f"[train_intraday] Entrenando {model_type.upper()} con {len(X)} muestras")
    print(f"[train_intraday]   Positivos: {y.sum()} ({y.mean():.2%})")
    
    if model_type == 'xgb' and HAS_XGB:
        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1
        )
    else:
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=50,
            min_samples_leaf=20,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'
        )
    
    model.fit(X, y)
    return model


def evaluate_model(model, X, y):
    """Evaluar modelo."""
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)[:, 1]
    
    print("\n[train_intraday] Métricas de entrenamiento:")
    print(classification_report(y, y_pred, target_names=['Loss', 'Win']))
    
    try:
        auc = roc_auc_score(y, y_proba)
        brier = brier_score_loss(y, y_proba)
        print(f"[train_intraday]   ROC AUC: {auc:.4f}")
        print(f"[train_intraday]   Brier Score: {brier:.4f}")
    except Exception as e:
        print(f"[train_intraday]   WARN: No se pudo calcular AUC/Brier: {e}")
    
    # Feature importance si es RF
    if hasattr(model, 'feature_importances_'):
        print("\n[train_intraday] Top 10 features:")
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1][:10]
        for i, idx in enumerate(indices):
            print(f"  {i+1}. Feature {idx}: {importances[idx]:.4f}")


def main():
    args = parse_args()
    config = load_config(args.config)
    
    # Obtener fechas
    dates = get_date_range(args.start, args.end)
    print(f"[train_intraday] Periodo: {args.start} a {args.end} ({len(dates)} días)")
    
    # Cargar datos
    df = load_training_data(dates, args.features_dir)
    if df is None or df.empty:
        print("[train_intraday] ERROR: No se pudieron cargar datos")
        return
    
    # Obtener features
    feature_cols = get_feature_columns(config)
    print(f"[train_intraday] Features: {len(feature_cols)}")
    
    # Preparar datos
    X, y = prepare_train_data(df, feature_cols)
    if X is None:
        print("[train_intraday] ERROR: No hay datos válidos después de limpieza")
        return
    
    if len(X) < args.min_samples:
        print(f"[train_intraday] ERROR: Insuficientes muestras ({len(X)} < {args.min_samples})")
        return
    
    # Escalar features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Entrenar
    model = train_model(X_scaled, y, args.model_type)
    
    # Evaluar
    evaluate_model(model, X_scaled, y)
    
    # Guardar
    os.makedirs(os.path.dirname(args.out_model), exist_ok=True)
    joblib.dump(model, args.out_model)
    joblib.dump(scaler, args.out_scaler)
    print(f"\n[train_intraday] Modelo guardado: {args.out_model}")
    print(f"[train_intraday] Scaler guardado: {args.out_scaler}")
    
    # Guardar metadata
    metadata = {
        'train_start': args.start,
        'train_end': args.end,
        'n_samples': len(X),
        'n_features': len(feature_cols),
        'feature_names': feature_cols,
        'win_rate': float(y.mean()),
        'model_type': args.model_type
    }
    
    metadata_file = args.out_model.replace('.joblib', '_metadata.yaml')
    with open(metadata_file, 'w') as f:
        yaml.dump(metadata, f)
    print(f"[train_intraday] Metadata guardada: {metadata_file}")


if __name__ == "__main__":
    main()
