#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_targets_and_eval.py

1) Construye y_H3/y_H5 por sesiones (shift -H) desde ohlcv_daily.csv
   - Acepta 'Close' o 'Adj Close' (usa la que exista)
2) Une a features del mes por (ticker,date) y calcula:
   y_H = (Close_fwd_H - entry_price) / entry_price
   (si falta entry_price, usa Close_t como base)
3) Evalúa return_model_H3/H5 si existen:
   - Usa exactamente feature_names_in_ si el modelo las expone
   - Si faltan columnas esperadas:
       * entry_price -> Close_t (si existe)
       * cualquier otra -> 0.0
   - Siempre genera predicciones para TODAS las filas (aunque no haya labels)
   - Solo calcula métricas si hay verdad-terreno (y_H*) disponible
Guarda:
   - CSV etiquetado (features + Close_t + Close_fwd_H* + y_H*)
   - reg_predictions_return_model_*.csv (muestra de predicciones)
   - reg_metrics_return_model_*.json (si hubo etiquetas)
"""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ---------------------------
# Utilidades de fecha/columnas
# ---------------------------

def coerce_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.tz_localize(None)

def _pick_close_column(df: pd.DataFrame) -> str:
    name_map = {c.lower(): c for c in df.columns}
    if "close" in name_map:
        return name_map["close"]
    if "adj close" in name_map:
        return name_map["adj close"]
    if "adjclose" in name_map:
        return name_map["adjclose"]
    raise ValueError(f"No se encontró columna Close/Adj Close. Columns={list(df.columns)[:12]}")

# ---------------------------
# Construcción de forward closes y targets
# ---------------------------

def build_forward(prices_csv: Path, horizons=(3, 5)) -> pd.DataFrame:
    df = pd.read_csv(prices_csv)
    cols = {c.lower(): c for c in df.columns}

    if "ticker" not in cols:
        raise ValueError(f"Falta 'ticker' en {prices_csv}. Columns={list(df.columns)[:12]}")
    if "date" not in cols and "datetime" not in cols:
        raise ValueError(f"Falta 'date' (o 'Datetime') en {prices_csv}. Columns={list(df.columns)[:12]}")

    tcol = cols["ticker"]
    dcol = cols["date"] if "date" in cols else cols["datetime"]
    ccol = _pick_close_column(df)

    df = df[[tcol, dcol, ccol]].rename(columns={tcol: "ticker", dcol: "date", ccol: "Close"})
    df["date"] = coerce_date(df["date"])
    df = df.dropna(subset=["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)

    out = df.rename(columns={"Close": "Close_t"}).copy()
    g = out.groupby("ticker", group_keys=False)
    for h in horizons:
        out[f"Close_fwd_H{h}"] = g["Close_t"].shift(-h)
    return out

def make_labeled(features_csv: Path, fwd_df: pd.DataFrame, horizons=(3, 5)) -> pd.DataFrame:
    f = pd.read_csv(features_csv)

    # normaliza ticker/date en features
    if "ticker" not in f.columns:
        tc = [c for c in f.columns if c.lower() == "ticker"]
        if tc: f = f.rename(columns={tc[0]: "ticker"})
    if "date" not in f.columns:
        dc = [c for c in f.columns if c.lower() == "date"]
        if dc: f = f.rename(columns={dc[0]: "date"})
    if "ticker" not in f.columns or "date" not in f.columns:
        raise ValueError("El features CSV debe tener 'ticker' y 'date'.")

    f["date"] = coerce_date(f["date"])
    m = pd.merge(f, fwd_df, on=["ticker", "date"], how="left")

    # base de precio: entry_price si existe; si no, Close_t
    base = m["entry_price"] if "entry_price" in m.columns else m["Close_t"]
    for h in horizons:
        m[f"y_H{h}"] = (m[f"Close_fwd_H{h}"] - base) / base
    return m

# ---------------------------
# Evaluación de regresión
# ---------------------------

def _ensure_expected_columns(X: pd.DataFrame, expected: list[str], context_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Garantiza que X tenga todas las columnas 'expected'.
    - Si falta 'entry_price' y existe Close_t en context, crea entry_price = Close_t.
    - Para el resto faltante, crea con 0.0.
    Devuelve (X_alineado, missing_que_fueron_creadas)
    """
    created = []
    for col in expected:
        if col in X.columns:
            continue
        # proxy especial para entry_price
        if col == "entry_price" and "Close_t" in context_df.columns:
            X[col] = context_df["Close_t"].values
            created.append(col)
        else:
            # relleno neutro 0.0
            X[col] = 0.0
            created.append(col)
    # Ordenar exactamente como expected
    X = X[expected]
    return X, created

def eval_reg(
    model_path: Path,
    df: pd.DataFrame,
    target: str,
    id_cols=("ticker", "date"),
    aux_cols=("Close_t", "Close_fwd_H3", "Close_fwd_H5"),
):
    """
    Evalúa y también predice, incluso si no hay verdad-terreno.
    - Si no hay filas con target no-nulo: guarda solo predicciones y salta métricas.
    - Si el modelo expone feature_names_in_: alinea exactamente esas columnas,
      creando proxies para faltantes (entry_price=Close_t; resto=0.0).
    """
    mdl = joblib.load(model_path)

    # Columnas esperadas por el modelo (si existen)
    expected = None
    for obj in (mdl, getattr(mdl, "named_steps", {}).get("pre", None)):
        if obj is not None and hasattr(obj, "feature_names_in_"):
            expected = list(obj.feature_names_in_)
            break

    # --- Construcción de X para TODO el dataset (predicciones) ---
    drop_pred = list(id_cols) + list(aux_cols)
    X_all = df.drop(columns=[c for c in drop_pred if c in df.columns], errors="ignore").copy()

    if expected is not None:
        X_all, created_all = _ensure_expected_columns(X_all, expected, context_df=df)
        if created_all:
            print(f"⚠️  (pred) Se crearon columnas faltantes: {created_all}")

    # Predicciones para todas las filas
    try:
        yhat_all = mdl.predict(X_all)
    except Exception as e:
        raise RuntimeError(f"Predicción (all rows) falló: {e}")

    # Guardar sample de predicciones (sin requerir target)
    cols_keep = [c for c in ("ticker", "date", "entry_price", "Close_t", target) if c in df.columns]
    pred_sample = df[cols_keep].copy() if cols_keep else pd.DataFrame(index=df.index)
    pred_sample["y_pred"] = yhat_all[: len(pred_sample)] if len(pred_sample) > 0 else yhat_all
    ppath = model_path.parent / f"reg_predictions_{model_path.stem}.csv"
    pred_sample.head(100).to_csv(ppath, index=False)

    # --- Evaluación solo con filas que sí tienen target ---
    if target not in df.columns:
        print(f"ℹ️  No existe columna '{target}'. Se guardaron predicciones, métricas omitidas.")
        return {"_skip": "target_missing"}, None, str(ppath)

    df_labeled = df.dropna(subset=[target]).copy()
    if df_labeled.empty:
        print(f"ℹ️  0 filas con verdad-terreno para '{target}'. Métricas omitidas; predicciones guardadas.")
        return {"_skip": "no_labels"}, None, str(ppath)

    # Construir X para el subconjunto etiquetado
    X_eval = df_labeled.drop(
        columns=[c for c in list(id_cols) + list(aux_cols) + [target] if c in df_labeled.columns],
        errors="ignore"
    ).copy()
    if expected is not None:
        X_eval, created_eval = _ensure_expected_columns(X_eval, expected, context_df=df_labeled)
        if created_eval:
            print(f"⚠️  (eval) Se crearon columnas faltantes: {created_eval}")

    y_true = df_labeled[target].astype(float).values
    try:
        y_pred = mdl.predict(X_eval)
    except Exception as e:
        raise RuntimeError(f"Predicción (eval) falló: {e}")

    # --- Métricas ---
    mae  = float(mean_absolute_error(y_true, y_pred))
    mse  = float(mean_squared_error(y_true, y_pred))
    rmse = float(np.sqrt(mse))  # compatible con todas las versiones
    r2   = float(r2_score(y_true, y_pred))
    mape = float(np.nanmean(np.abs((y_true - y_pred) / np.where(y_true != 0, y_true, np.nan))) * 100.0)

    metrics = {"MAE": mae, "RMSE": rmse, "R2": r2, "MAPE_pct": mape, "rows": int(len(df_labeled))}
    mpath = model_path.parent / f"reg_metrics_{model_path.stem}.json"
    mpath.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    return metrics, str(mpath), str(ppath)

# ---------------------------
# Main
# ---------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-csv", required=True)
    ap.add_argument("--prices-csv", required=True)
    ap.add_argument("--out-labeled", required=True)
    ap.add_argument("--model-h3", default="models/return_model_H3.joblib")
    ap.add_argument("--model-h5", default="models/return_model_H5.joblib")
    ap.add_argument("--horizons", nargs="*", type=int, default=[3, 5])
    args = ap.parse_args()

    # 1) Forward closes
    fwd = build_forward(Path(args.prices_csv), horizons=args.horizons)

    # 2) Labeled (features + targets)
    labeled = make_labeled(Path(args.features_csv), fwd, horizons=args.horizons)
    outp = Path(args.out_labeled)
    outp.parent.mkdir(parents=True, exist_ok=True)
    labeled.to_csv(outp, index=False)
    print(f"✅ Labeled listo: {outp} (rows={len(labeled)})")

    # 3) Evaluación H3 / H5 si existen
    for H, model_path in [(3, Path(args.model_h3)), (5, Path(args.model_h5))]:
        if model_path.exists():
            metrics, mpath, ppath = eval_reg(model_path, labeled, f"y_H{H}")
            print(f"🏁 H{H} → {metrics}")
            if mpath: print(f"   📄 {mpath}")
            if ppath: print(f"   📄 {ppath}")
        else:
            print(f"ℹ️ No se encontró modelo {model_path}, se omite.")

if __name__ == "__main__":
    main()
