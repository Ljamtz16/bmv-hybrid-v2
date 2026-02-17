# scripts/22_train_return_model.py
import argparse
import json
import re
from typing import List, Dict

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib
import warnings

warnings.filterwarnings("ignore")

# Columnas que nunca deben usarse como features
BASE_DROP_COLS = {
    "date", "ticker", "signal_id", "y", "target", "win",
    "future_high", "future_low", "future_close",
}

def parse_horizons(s: str) -> List[int]:
    try:
        vals = [int(x.strip()) for x in s.split(",") if x.strip()]
        assert all(v > 0 for v in vals)
        return sorted(set(vals))
    except Exception:
        raise argparse.ArgumentTypeError("Usa un formato válido, p. ej.: '1,3,5,10' (enteros > 0)")

def collect_feature_cols(df: pd.DataFrame, target_cols: List[str]) -> List[str]:
    """Elige solo columnas numéricas y evita targets/columnas bloqueadas."""
    drop_cols = set(BASE_DROP_COLS) | set(target_cols)
    # Evita cualquier columna que parezca target_return_* de otros horizontes
    drop_cols |= {c for c in df.columns if re.match(r"^target_return_\d+d(_volnorm)?$", c)}
    feats = [c for c in df.columns if c not in drop_cols]
    feats_num = df[feats].select_dtypes(include=[np.number]).columns.tolist()
    return feats_num

def train_one_horizon(df: pd.DataFrame, H: int, kind: str, n_splits: int,
                      model_path: str, features_path: str) -> Dict:
    """
    Entrena un modelo para el horizonte H (raw o volnorm) y lo guarda.
    Retorna dict con métricas, mejor configuración y rutas.
    """
    assert kind in {"raw", "volnorm"}
    target_col = f"target_return_{H}d" + ("_volnorm" if kind == "volnorm" else "")

    if target_col not in df.columns:
        raise SystemExit(f"❌ No encontré la columna objetivo '{target_col}'. "
                         f"Genera los targets con 20b_add_return_targets.py (horizonte {H}).")

    # Orden temporal por seguridad
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
    # Filtrar filas válidas para este target
    dfx = df.dropna(subset=[target_col]).copy()

    # Elegir features
    feature_cols = collect_feature_cols(dfx, target_cols=[target_col])
    if not feature_cols:
        raise SystemExit("❌ No hay columnas numéricas válidas para entrenar.")

    X = dfx[feature_cols]
    y = dfx[target_col].astype(float)

    # Preprocesamiento
    numeric = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    pre = ColumnTransformer(
        transformers=[("num", numeric, feature_cols)],
        remainder="drop"
    )

    rf = RandomForestRegressor(n_estimators=500, random_state=42, n_jobs=-1)
    pipe = Pipeline(steps=[("pre", pre), ("rf", rf)])

    param_dist = {
        "rf__n_estimators": [300, 500, 800],
        "rf__max_depth": [6, 8, 12, None],
        "rf__min_samples_split": [2, 5, 10],
        "rf__min_samples_leaf": [1, 2, 4],
        "rf__max_features": ["sqrt", "log2", None],
    }

    tscv = TimeSeriesSplit(n_splits=n_splits)
    search = RandomizedSearchCV(
        pipe,
        param_distributions=param_dist,
        n_iter=20,
        cv=tscv,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
        random_state=42,
        verbose=1,
    )
    search.fit(X, y)
    best_model = search.best_estimator_

    # Evaluación holdout temporal (20% final)
    cutoff = int(len(dfx) * 0.8)
    X_train, X_test = X.iloc[:cutoff], X.iloc[cutoff:]
    y_train, y_test = y.iloc[:cutoff], y.iloc[cutoff:]
    best_model.fit(X_train, y_train)
    y_pred = best_model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    # Guardado
    joblib.dump(best_model, model_path)
    meta = {"features": feature_cols, "target": target_col}
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"\n✅ H={H} ({kind}) → modelo: {model_path}")
    print(f"   📏 MAE: {mae:.6f} | 📈 R²: {r2:.4f}")
    print(f"   🧪 best_params: {search.best_params_}")
    return {
        "H": H,
        "kind": kind,
        "target": target_col,
        "mae": float(mae),
        "r2": float(r2),
        "best_params": search.best_params_,
        "model_path": model_path,
        "features_path": features_path,
        "n_train": int(cutoff),
        "n_test": int(len(dfx) - cutoff),
        "n_total_rows": int(len(dfx)),
        "n_features": len(feature_cols),
    }

def main():
    ap = argparse.ArgumentParser(
        description="Entrena modelos de regresión de retorno para uno o varios horizontes H."
    )
    ap.add_argument("--data", default="reports/forecast/training_dataset_w_returns.csv",
                    help="CSV con targets creados por 20b_add_return_targets.py")
    ap.add_argument("--horizons", type=parse_horizons, default=[5],
                    help="Lista de horizontes H, ej. 1,3,5,10 (default: 5)")
    ap.add_argument("--kind", choices=["raw", "volnorm"], default="raw",
                    help="Target: raw=target_return_Hd | volnorm=target_return_Hd_volnorm")
    ap.add_argument("--models_dir", default="models",
                    help="Directorio donde guardar modelos y metadatos")
    ap.add_argument("--report_csv", default="models/return_models_report.csv",
                    help="Ruta del CSV con resumen de métricas")
    ap.add_argument("--n_splits", type=int, default=5,
                    help="N° de particiones para TimeSeriesSplit (default: 5)")
    args = ap.parse_args()

    df = pd.read_csv(args.data, parse_dates=["date"])
    print(f"• Data: {args.data} | filas: {len(df):,}")

    results = []
    for H in args.horizons:
        model_path = f"{args.models_dir}/return_model_H{H}.joblib"
        features_path = f"{args.models_dir}/return_model_H{H}_features.json"
        res = train_one_horizon(
            df=df,
            H=H,
            kind=args.kind,
            n_splits=args.n_splits,
            model_path=model_path,
            features_path=features_path,
        )
        results.append(res)

    # Guardar reporte
    rep_df = pd.DataFrame(results).sort_values(["kind", "H"]).reset_index(drop=True)
    rep_df.to_csv(args.report_csv, index=False)
    print(f"\n📝 Reporte guardado: {args.report_csv}")
    print(rep_df[["H", "kind", "target", "mae", "r2", "n_features", "n_total_rows"]])

if __name__ == "__main__":
    main()
