# Script 04 — Train Intraday Model
# Entrena modelo de regresión logística para prob_win_intraday
#
# Input:  artifacts/intraday_ml_dataset.parquet
# Output: models/intraday_probwin_model.pkl
#         models/intraday_feature_columns.json
#         evidence/train_intraday_report.json

import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss, average_precision_score
from sklearn.calibration import CalibratedClassifierCV
import joblib


def train_intraday_model(
    dataset_path: str,
    model_path: str,
    features_path: str,
    report_path: str,
    train_end_date: str = '2025-06-30',
    val_start_date: str = '2025-07-01'
) -> dict:
    """
    Entrena modelo intraday con split temporal.
    
    Returns:
        dict con métricas y metadata
    """
    print(f"[04] Cargando dataset desde {dataset_path}...")
    df = pd.read_parquet(dataset_path)
    
    print(f"[04] Filas totales: {len(df):,}")
    print(f"[04] Columnas: {df.columns.tolist()}")
    
    # Convertir date a datetime para split
    df['date'] = pd.to_datetime(df['date'])
    
    # === Features ===
    # Solo usar features prev y de ventana (sin leakage)
    feature_cols = [
        'atr14',  # ya es prev (renombrado en 03)
        'ema20',  # ya es prev (renombrado en 03)
        'daily_range_pct',  # ya es prev
        'is_high_vol',  # ya es prev
        'is_wide_range',  # ya es prev
        'is_directional',  # ya es prev
        'window_range',
        'window_return',
        'window_body',
        'w_close_vs_ema',
        'range_to_atr',
        'body_to_atr',
        'n_bars',
        'gap_atr',
        'overnight_ret',
        'rvol',
        'vwap_dist',
        'body_to_atr_x_high_vol',
        'range_to_atr_x_directional'
    ]
    
    # Agregar side_prev como numeric (BUY=1, SELL=0)
    df['side_numeric'] = (df['side'] == 'BUY').astype(int)
    feature_cols.append('side_numeric')
    
    # Agregar window como one-hot
    df['window_OPEN'] = (df['window'] == 'OPEN').astype(int)
    df['window_CLOSE'] = (df['window'] == 'CLOSE').astype(int)
    feature_cols.extend(['window_OPEN', 'window_CLOSE'])
    
    # Verificar features disponibles
    missing = set(feature_cols) - set(df.columns)
    if missing:
        raise ValueError(f"Features faltantes: {missing}")
    
    print(f"\n[04] Features usadas ({len(feature_cols)}): {feature_cols}")
    
    # === Split temporal ===
    train_mask = df['date'] <= train_end_date
    val_mask = df['date'] >= val_start_date
    
    df_train = df[train_mask].copy()
    df_val = df[val_mask].copy()
    
    print(f"\n[04] === SPLIT TEMPORAL ===")
    print(f"[04] Train: {df_train['date'].min()} → {df_train['date'].max()} | {len(df_train):,} filas")
    print(f"[04] Val:   {df_val['date'].min()} → {df_val['date'].max()} | {len(df_val):,} filas")
    
    if len(df_train) == 0 or len(df_val) == 0:
        raise ValueError("Split temporal resultó en train o val vacío")
    
    # Preparar X, y
    X_train = df_train[feature_cols].copy()
    y_train = df_train['y'].copy()
    
    X_val = df_val[feature_cols].copy()
    y_val = df_val['y'].copy()
    
    # === Time-decay sample weighting ===
    # Dar más peso a muestras recientes para mejorar calibración
    lambda_decay = 0.001
    max_date = df_train['date'].max()
    age_days_train = (max_date - df_train['date']).dt.days
    sample_weights_train = np.exp(-lambda_decay * age_days_train)
    
    # Drop NaN (por si acaso)
    train_valid = ~(X_train.isna().any(axis=1) | y_train.isna())
    val_valid = ~(X_val.isna().any(axis=1) | y_val.isna())
    
    X_train = X_train[train_valid]
    y_train = y_train[train_valid]
    X_val = X_val[val_valid]
    y_val = y_val[val_valid]
    sample_weights_train = sample_weights_train[train_valid]
    
    print(f"[04] Después de drop NaN: Train {len(X_train):,} | Val {len(X_val):,}")
    
    # === Modelo ===
    print(f"\n[04] Entrenando LogisticRegression con class_weight='balanced'...")
    
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(
            max_iter=2000,
            class_weight='balanced',
            random_state=42,
            solver='lbfgs'
        ))
    ])
    
    pipeline.fit(X_train, y_train, model__sample_weight=sample_weights_train)
    
    # === Probability Calibration (Isotonic Regression) ===
    print(f"\n[04] Calibrando probabilidades con Isotonic Regression...")
    calibrator = CalibratedClassifierCV(
        estimator=pipeline,
        method='isotonic',
        cv='prefit'
    )
    calibrator.fit(X_val, y_val)
    
    # === Predicciones ===
    y_train_proba = pipeline.predict_proba(X_train)[:, 1]
    y_val_proba = pipeline.predict_proba(X_val)[:, 1]
    
    # Predicciones calibradas
    y_train_proba_cal = calibrator.predict_proba(X_train)[:, 1]
    y_val_proba_cal = calibrator.predict_proba(X_val)[:, 1]
    
    # === Métricas ===
    print(f"\n[04] === MÉTRICAS ===")
    
    # Train
    auc_train = roc_auc_score(y_train, y_train_proba)
    brier_train = brier_score_loss(y_train, y_train_proba)
    ap_train = average_precision_score(y_train, y_train_proba)
    
    print(f"[04] TRAIN | AUC: {auc_train:.4f} | Brier: {brier_train:.4f} | AP: {ap_train:.4f}")
    
    # Train Calibrated
    auc_train_cal = roc_auc_score(y_train, y_train_proba_cal)
    brier_train_cal = brier_score_loss(y_train, y_train_proba_cal)
    ap_train_cal = average_precision_score(y_train, y_train_proba_cal)
    
    print(f"[04] TRAIN Cal | AUC: {auc_train_cal:.4f} | Brier: {brier_train_cal:.4f} | AP: {ap_train_cal:.4f}")
    
    # Val
    auc_val = roc_auc_score(y_val, y_val_proba)
    brier_val = brier_score_loss(y_val, y_val_proba)
    ap_val = average_precision_score(y_val, y_val_proba)
    
    print(f"[04] VAL   | AUC: {auc_val:.4f} | Brier: {brier_val:.4f} | AP: {ap_val:.4f}")
    
    # Val Calibrated
    auc_val_cal = roc_auc_score(y_val, y_val_proba_cal)
    brier_val_cal = brier_score_loss(y_val, y_val_proba_cal)
    ap_val_cal = average_precision_score(y_val, y_val_proba_cal)
    
    print(f"[04] VAL Cal   | AUC: {auc_val_cal:.4f} | Brier: {brier_val_cal:.4f} | AP: {ap_val_cal:.4f}")
    
    # === ECE (Expected Calibration Error) ===
    def _ece(y_true, y_pred, n_bins=10):
        """Calcula Expected Calibration Error"""
        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            in_bin = (y_pred >= bin_edges[i]) & (y_pred < bin_edges[i + 1])
            if in_bin.sum() == 0:
                continue
            acc = y_true[in_bin].mean()
            conf = y_pred[in_bin].mean()
            ece += in_bin.sum() / len(y_true) * abs(acc - conf)
        return ece
    
    ece_train_cal = _ece(y_train.values, y_train_proba_cal)
    ece_val_cal = _ece(y_val.values, y_val_proba_cal)
    print(f"[04] ECE (Calibrated) | Train: {ece_train_cal:.4f} | Val: {ece_val_cal:.4f}")
    
    # Baseline Brier (predecir siempre la tasa positiva)
    baseline_proba_train = y_train.mean()
    baseline_proba_val = y_val.mean()
    brier_baseline_train = brier_score_loss(y_train, [baseline_proba_train] * len(y_train))
    brier_baseline_val = brier_score_loss(y_val, [baseline_proba_val] * len(y_val))
    
    print(f"[04] Brier Baseline | Train: {brier_baseline_train:.4f} | Val: {brier_baseline_val:.4f}")
    
    # Distribución de probas
    train_proba_stats = pd.Series(y_train_proba).describe(percentiles=[0.1, 0.5, 0.9])
    val_proba_stats = pd.Series(y_val_proba).describe(percentiles=[0.1, 0.5, 0.9])
    
    print(f"\n[04] Distribución prob_win_intraday (TRAIN):\n{train_proba_stats}")
    print(f"\n[04] Distribución prob_win_intraday (VAL):\n{val_proba_stats}")
    
    # Coeficientes (top features)
    lr_model = pipeline.named_steps['model']
    coefs = pd.DataFrame({
        'feature': feature_cols,
        'coef': lr_model.coef_[0]
    }).sort_values('coef', key=abs, ascending=False)
    
    print(f"\n[04] Top 10 Features (por |coef|):")
    print(coefs.head(10))
    
    # === Guardar ===
    model_dir = Path(model_path).parent
    features_dir = Path(features_path).parent
    report_dir = Path(report_path).parent
    
    model_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    # Modelo
    joblib.dump(pipeline, model_path)
    print(f"\n[04] ✅ Modelo guardado en: {model_path}")
    
    # Calibrator
    calibrator_path = str(model_path).replace('_model.pkl', '_calibrator.pkl')
    joblib.dump(calibrator, calibrator_path)
    print(f"[04] ✅ Calibrador guardado en: {calibrator_path}")
    
    # Features
    with open(features_path, 'w') as f:
        json.dump(feature_cols, f, indent=2)
    print(f"[04] ✅ Features guardadas en: {features_path}")
    
    # Report
    report = {
        'train_date_range': [str(df_train['date'].min()), str(df_train['date'].max())],
        'val_date_range': [str(df_val['date'].min()), str(df_val['date'].max())],
        'train_samples': len(X_train),
        'val_samples': len(X_val),
        'features': feature_cols,
        'metrics': {
            'train': {
                'auc': float(auc_train),
                'brier': float(brier_train),
                'average_precision': float(ap_train),
                'brier_baseline': float(brier_baseline_train)
            },
            'val': {
                'auc': float(auc_val),
                'brier': float(brier_val),
                'average_precision': float(ap_val),
                'brier_baseline': float(brier_baseline_val)
            },
            'train_calibrated': {
                'auc': float(auc_train_cal),
                'brier': float(brier_train_cal),
                'average_precision': float(ap_train_cal),
                'ece': float(ece_train_cal)
            },
            'val_calibrated': {
                'auc': float(auc_val_cal),
                'brier': float(brier_val_cal),
                'average_precision': float(ap_val_cal),
                'ece': float(ece_val_cal)
            }
        },
        'proba_distribution': {
            'train': {k: float(v) for k, v in train_proba_stats.items()},
            'val': {k: float(v) for k, v in val_proba_stats.items()}
        },
        'top_features': coefs.head(10).to_dict('records'),
        'policy_params': {
            'tp_mult': 0.8,
            'sl_mult': 0.6,
            'time_stop_bars': 16
        },
        'calibration': {
            'method': 'isotonic',
            'lambda_decay': lambda_decay
        },
        'threshold_default': 0.60
    }
    
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"[04] ✅ Report guardado en: {report_path}")
    
    return report


if __name__ == '__main__':
    DATASET_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    MODEL_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\models\intraday_probwin_model.pkl'
    FEATURES_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\models\intraday_feature_columns.json'
    REPORT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\evidence\train_intraday_report.json'
    
    report = train_intraday_model(
        DATASET_FILE,
        MODEL_FILE,
        FEATURES_FILE,
        REPORT_FILE,
        train_end_date='2025-06-30',
        val_start_date='2025-07-01'
    )
    
    print(f"\n[04] === RESUMEN ===")
    print(f"[04] Train AUC: {report['metrics']['train']['auc']:.4f}")
    print(f"[04] Val AUC: {report['metrics']['val']['auc']:.4f}")
    print(f"[04] Val AUC Calibrated: {report['metrics']['val_calibrated']['auc']:.4f}")
    print(f"[04] ECE (Calibrated): {report['metrics']['val_calibrated']['ece']:.4f}")
    print(f"[04] Threshold default para plan: {report['threshold_default']}")
