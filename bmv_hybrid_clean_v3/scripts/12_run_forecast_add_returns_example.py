# scripts/12_run_forecast_add_returns_example.py
from __future__ import annotations

# --- bootstrap para importar 'src' si hace falta ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# ---------------------------------------------------

import argparse, json
import pandas as pd
import numpy as np
import joblib


def _read_features(path: Path) -> pd.DataFrame:
    """
    Lee el CSV de features de forma robusta y convierte columnas de fecha si existen.
    """
    # Lee una fila para detectar columnas
    hdr = pd.read_csv(path, nrows=0)
    date_candidates = [c for c in ["date", "entry_date"] if c in hdr.columns]

    df = pd.read_csv(path, parse_dates=date_candidates)
    # Normalizaciones mínimas útiles en el resto del pipeline
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str)
    if "side" in df.columns:
        df["side"] = df["side"].astype(str).str.upper()

    return df


def main():
    ap = argparse.ArgumentParser(
        description="Aplica el modelo de retorno H al CSV de features del forecast y calcula expected value."
    )
    ap.add_argument("--H", type=int, required=True, help="Horizonte en días (ej. 3)")
    ap.add_argument("--features_csv", default="reports/forecast/latest_forecast_features.csv")
    ap.add_argument("--out", default="reports/forecast/latest_forecast_with_returns.csv")
    ap.add_argument("--models_dir", default="models")
    ap.add_argument("--prob_col", default="prob_win", help="Columna con prob. de acierto (default: prob_win)")
    ap.add_argument("--ev_col", default="expected_value", help="Nombre de la columna EV")
    args = ap.parse_args()

    H = int(args.H)
    model_path = Path(args.models_dir) / f"return_model_H{H}.joblib"
    feat_meta  = Path(args.models_dir) / f"return_model_H{H}_features.json"
    feat_csv   = Path(args.features_csv)

    if not feat_csv.exists():
        raise SystemExit(f"❌ No encontré features_csv: {feat_csv}")
    if not model_path.exists():
        raise SystemExit(f"❌ No encontré el modelo: {model_path}. Entrénalo con 22_train_return_model.py.")
    if not feat_meta.exists():
        raise SystemExit(f"❌ No encontré metadata de features: {feat_meta}.")

    # Carga modelo y metadata
    model = joblib.load(model_path)
    with open(feat_meta, "r", encoding="utf-8") as f:
        meta = json.load(f)
    feature_cols = meta.get("features", [])
    target_name  = meta.get("target", f"target_return_{H}d")

    # Carga features de forma robusta
    df = _read_features(feat_csv)
    if df.empty:
        raise SystemExit("❌ features_csv está vacío.")

    # Asegura features esperadas por el modelo
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        for c in missing:
            df[c] = 0.0
        print(f"⚠️ Faltaban {len(missing)} features, se rellenaron con 0: {missing[:10]}{'...' if len(missing)>10 else ''}")

    # Predicción del retorno H
    X = df[feature_cols].copy()
    pred_col = f"pred_return_{H}d"
    df[pred_col] = model.predict(X).astype(float)

    # ------- Probabilidad: garantizar 'prob_win' y 'prob' -------
    # 1) Elegir la fuente de probabilidad
    prob_series = None
    # a) Si viene la que indicó el usuario
    if args.prob_col in df.columns:
        prob_series = pd.to_numeric(df[args.prob_col], errors="coerce")
    # b) Si no, intenta 'prob_win'
    elif "prob_win" in df.columns:
        prob_series = pd.to_numeric(df["prob_win"], errors="coerce")
    # c) Si no, intenta 'prob'
    elif "prob" in df.columns:
        prob_series = pd.to_numeric(df["prob"], errors="coerce")

    # 2) Fallback a 0.5 si no hay ninguna
    if prob_series is None:
        print(f"⚠️ No encontré columna de probabilidad ('{args.prob_col}', 'prob_win' o 'prob'); usaré 0.5 como base.")
        prob_series = pd.Series(0.5, index=df.index, dtype=float)

    # 3) Limpieza y clip
    prob_series = prob_series.fillna(0.5).clip(0, 1).astype(float)

    # 4) Asegurar que existan ambas columnas en la salida
    df["prob_win"] = prob_series  # siempre existirán en salida
    df["prob"]     = prob_series  # alias para scripts que esperan 'prob'

    # EV básico
    df[args.ev_col] = df["prob_win"] * df[pred_col]

    # Orden amable si existen estas columnas
    lead = [c for c in ["ticker", "date", "side", "prob_win", "prob", pred_col, args.ev_col] if c in df.columns]
    cols = lead + [c for c in df.columns if c not in lead]
    df = df[cols]

    # Guardar
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"✅ Guardado con predicción y EV: {out} (filas={len(df):,})")


if __name__ == "__main__":
    main()
