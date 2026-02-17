# -*- coding: utf-8 -*-
"""
Entrenamiento intradía robusto (sin fugas) con BalancedRandomForest
- Split por fecha (GroupShuffleSplit) para evitar fuga temporal
- Pipeline: ColumnTransformer(StandardScaler) -> [SMOTE opcional] -> BRF
- Calibración isotónica en validación
- Métricas: ROC-AUC, PR-AUC, Brier, Precision@k

Uso:
  python scripts/10_train_intraday_brf.py --start 2025-09-01 --end 2025-10-31 \
    --use-smote false --k-top 20 --models-dir models
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np

from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.compose import ColumnTransformer
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.pipeline import Pipeline as SkPipeline
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.impute import SimpleImputer

from imblearn.ensemble import BalancedRandomForestClassifier
from imblearn.over_sampling import SMOTE

from joblib import dump
import json


def list_feature_files(root: Path, start: str, end: str):
    start_dt = pd.to_datetime(start).date()
    end_dt = pd.to_datetime(end).date()
    files = []
    idir = root
    if not idir.exists():
        raise FileNotFoundError(f"No existe {idir}")
    for f in idir.glob("*.parquet"):
        try:
            date_str = f.stem  # YYYY-MM-DD
            d = pd.to_datetime(date_str).date()
            if start_dt <= d <= end_dt:
                files.append(f)
        except Exception:
            continue
    files = sorted(files, key=lambda p: p.name)
    return files


def load_dataset(files):
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except Exception as e:
            print(f"WARN: fallo leyendo {f.name}: {e}")
    if not dfs:
        raise RuntimeError("Sin datos para entrenar")
    df = pd.concat(dfs, ignore_index=True)
    # Derivar fecha (group) para split
    if 'timestamp' in df.columns:
        df['date'] = pd.to_datetime(df['timestamp']).dt.date.astype(str)
    else:
        df['date'] = 'unknown'
    return df


def pick_feature_columns(df: pd.DataFrame):
    # Lista candidata basada en tus features reales
    candidates = [
        'RSI_14','EMA_9','EMA_20','EMA_50','MACD','MACD_signal','MACD_hist',
        'ATR_14','ATR_pct','BB_middle','BB_upper','BB_lower','BB_width',
        'volume_ratio','volume_zscore','VWAP_dev','spread_bps','turnover_ratio',
        'hour','minute','dist_to_open','dist_to_close','time_numeric',
        'is_first_hour','is_last_hour','ret_30m','ret_60m','ret_120m'
    ]
    cols = [c for c in candidates if c in df.columns]
    # Agregar direction si existe (num)
    if 'direction' in df.columns:
        df['direction_num'] = df['direction'].map({'LONG':1,'SHORT':0}).fillna(0)
        cols.append('direction_num')
    # Fallback: si no hay candidatos, usa todas numéricas seguras
    if not cols:
        exclude = {'win','timestamp','date','ticker','symbol','policy','tag','side','entry_time','exit_time'}
        num_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]
        cols = num_cols
    return cols


def build_pipeline(num_cols, use_smote: bool):
    pre = ColumnTransformer([
        ("num", SkPipeline([
            ("imp", SimpleImputer(strategy='median')),
            ("sc", StandardScaler(with_mean=True, with_std=True))
        ]), num_cols)
    ], remainder='drop')

    clf = BalancedRandomForestClassifier(
        n_estimators=600,
        max_depth=None,
        min_samples_leaf=2,
        class_weight=None,  # BRF ya balancea
        n_jobs=-1,
        random_state=42
    )

    steps = [("prep", pre)]
    if use_smote:
        steps.append(("smote", SMOTE(k_neighbors=5, random_state=42)))
    steps.append(("clf", clf))

    pipe = ImbPipeline(steps)
    return pipe


def precision_at_k(y_true, y_prob, k=20):
    if len(y_prob) == 0:
        return 0.0
    k = min(k, len(y_prob))
    idx = np.argsort(y_prob)[::-1][:k]
    return float(y_true[idx].mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--features-dir", default="features/intraday")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--use-smote", action='store_true')
    ap.add_argument("--k-top", type=int, default=20)
    args = ap.parse_args()

    files = list_feature_files(Path(args.features_dir), args.start, args.end)
    print(f"[train_brf] Archivos: {len(files)}")
    df = load_dataset(files)

    # Target
    if 'win' not in df.columns:
        raise RuntimeError("Columna 'win' no encontrada")
    y = df['win'].astype(int).values

    # Features
    feat_cols = pick_feature_columns(df)
    if not feat_cols:
        raise RuntimeError("Sin columnas de features válidas")
    X = df[feat_cols].copy()

    # Grupos por fecha para split
    groups = df['date'].values

    # Split
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, va_idx = next(gss.split(X, y, groups=groups))

    X_tr, y_tr = X.iloc[tr_idx], y[tr_idx]
    X_va, y_va = X.iloc[va_idx], y[va_idx]

    print(f"[train_brf] Train: {len(X_tr)}, Val: {len(X_va)}")
    print(f"[train_brf] Win rate Train: {y_tr.mean()*100:.2f}%, Val: {y_va.mean()*100:.2f}%")

    # Pipeline
    pipe = build_pipeline(feat_cols, use_smote=args.use_smote)
    pipe.fit(X_tr, y_tr)

    # Métricas en val
    p_va = pipe.predict_proba(X_va)[:,1]
    roc = roc_auc_score(y_va, p_va)
    pr = average_precision_score(y_va, p_va)
    brier = brier_score_loss(y_va, p_va)
    p_at_k = precision_at_k(y_va, p_va, k=args.k_top)

    print(f"\n[train_brf] Métricas VAL:")
    print(f"  ROC-AUC:  {roc:.4f}")
    print(f"  PR-AUC:   {pr:.4f}")
    print(f"  Brier:    {brier:.4f}")
    print(f"  P@{args.k_top}: {p_at_k:.3f}")

    # Calibración en val
    cal = CalibratedClassifierCV(estimator=pipe, method='isotonic', cv='prefit')
    cal.fit(X_va, y_va)

    # Guardar
    outdir = Path(args.models_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    model_path = outdir / 'clf_intraday_brf_calibrated.joblib'
    dump(cal, model_path)

    meta = {
        'features': feat_cols,
        'use_smote': bool(args.use_smote),
        'start': args.start,
        'end': args.end,
        'val_metrics': {
            'roc_auc': float(roc),
            'pr_auc': float(pr),
            'brier': float(brier),
            f'precision_at_{args.k_top}': float(p_at_k)
        }
    }
    with open(outdir / 'clf_intraday_brf_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    print(f"\n[train_brf] Modelo calibrado guardado en {model_path}")


if __name__ == "__main__":
    main()
