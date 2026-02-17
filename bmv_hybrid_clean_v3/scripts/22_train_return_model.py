# scripts/22_train_return_model.py
from __future__ import annotations
import argparse, json, re, warnings
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

warnings.filterwarnings("ignore")

# Columnas que nunca deben ser features
BASE_DROP_COLS = {
    "ticker", "signal_id", "y", "target", "win",
    "future_high", "future_low", "future_close",
    # agrega aquí si tienes columnas administrativas que no deban entrar
}

def parse_horizons(s: str) -> List[int]:
    vals = []
    for tok in s.replace(",", " ").split():
        v = int(tok)
        if v <= 0:
            raise argparse.ArgumentTypeError("Horizons deben ser enteros > 0.")
        vals.append(v)
    return sorted(set(vals))

def collect_feature_cols(df: pd.DataFrame, target_cols: List[str]) -> List[str]:
    """Elige columnas numéricas y elimina targets/columnas bloqueadas."""
    drop_cols = set(BASE_DROP_COLS) | set(target_cols)
    # Evita cualquier columna target de otros horizontes:
    drop_cols |= {c for c in df.columns if re.match(r"^target_return_\d+d(_volnorm)?$", c)}
    # Evita columnas típicas de fecha
    drop_cols |= {"date", "entry_date", "exit_date"}

    feats = [c for c in df.columns if c not in drop_cols]
    feats_num = df[feats].select_dtypes(include=[np.number]).columns.tolist()
    return feats_num

def train_one_horizon(
    df: pd.DataFrame,
    date_col: str,
    H: int,
    kind: str,
    n_splits: int,
    model_path: str,
    features_path: str
) -> Dict:
    assert kind in {"raw", "volnorm"}
    target_col = f"target_return_{H}d" + ("_volnorm" if kind == "volnorm" else "")

    if target_col not in df.columns:
        raise SystemExit(
            f"❌ No encontré '{target_col}'. Genera targets con 20b_add_return_targets.py (incluye H={H})."
        )

    # Orden temporal y filtrado de filas válidas
    df = df.sort_values([date_col, "ticker"]).reset_index(drop=True)
    dfx = df.dropna(subset=[target_col]).copy()

    # Features numéricas válidas
    feature_cols = collect_feature_cols(dfx, target_cols=[target_col])
    if not feature_cols:
        raise SystemExit("❌ No hay columnas numéricas válidas para entrenar.")

    X = dfx[feature_cols]
    y = dfx[target_col].astype(float)

    # Preprocesamiento + modelo
    numeric = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    pre = ColumnTransformer(transformers=[("num", numeric, feature_cols)], remainder="drop")

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

    # Holdout temporal sencillo (20% final)
    cutoff = int(len(dfx) * 0.8)
    X_train, X_test = X.iloc[:cutoff], X.iloc[cutoff:]
    y_train, y_test = y.iloc[:cutoff], y.iloc[cutoff:]
    best_model.fit(X_train, y_train)
    y_pred = best_model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    # Guardar modelo y metadata
    joblib.dump(best_model, model_path)
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump({"features": feature_cols, "target": target_col}, f, indent=2, ensure_ascii=False)

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
        "n_total_rows": int(len(dfx)),
        "n_features": len(feature_cols),
    }

def add_return_features(df):
    # Volatilidad 20d
    if "close" in df.columns:
        df["vol_20d"] = df["close"].rolling(20).std()
    # Momentum 5d
    if "close" in df.columns:
        df["momentum_5d"] = df["close"] - df["close"].shift(5)
    # Spreads relativos
    if "high" in df.columns and "low" in df.columns and "close" in df.columns:
        df["spread"] = (df["high"] - df["low"]) / df["close"]
    return df

def main():
    ap = argparse.ArgumentParser(
        description="Entrena modelos de regresión de retorno para uno o varios horizontes."
    )
    ap.add_argument("--data", default="reports/forecast/training_dataset_w_returns.csv",
                    help="CSV con targets creados por 20b_add_return_targets.py")
    ap.add_argument("--horizons", default="5",
                    help="Lista de horizontes H, ej. 1,3,5,10 (default: 5)")
    ap.add_argument("--kind", choices=["raw", "volnorm"], default="raw",
                    help="Target: raw=target_return_Hd | volnorm=target_return_Hd_volnorm")
    ap.add_argument("--date-col", default="entry_date",
                    help="Columna de fecha para ordenar temporalmente (default: entry_date)")
    ap.add_argument("--models_dir", default="models",
                    help="Directorio de salida para los modelos")
    ap.add_argument("--report_csv", default="models/return_models_report.csv",
                    help="Resumen de métricas por H")
    ap.add_argument("--n_splits", type=int, default=5,
                    help="Particiones para TimeSeriesSplit")
    args = ap.parse_args()

    horizons = parse_horizons(args.horizons)

    # Cargar dataset (parsea la fecha indicada)
    parse_dates = [args.date_col] if args.date_col else None
    df = pd.read_csv(args.data, parse_dates=parse_dates)
    if args.date_col not in df.columns:
        raise SystemExit(f"❌ No encontré la columna de fecha '{args.date_col}' en {args.data}.")

    # Agregar features de volatilidad, momentum y spreads
    df = add_return_features(df)

    print(f"• Data: {args.data} | filas: {len(df):,} | date_col={args.date_col}")
    results = []

    for H in horizons:
        model_path = f"{args.models_dir}/return_model_H{H}.joblib"
        features_path = f"{args.models_dir}/return_model_H{H}_features.json"
        res = train_one_horizon(
            df=df,
            date_col=args.date_col,
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
