#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inferencia y gate de señales a partir de un modelo de regresión (y_hat)
y opcionalmente un modelo de probabilidad (prob_win).

Características:
- Carga CSV de features (idealmente el "labeled" del paso 2).
- Alinea columnas esperadas por el pipeline; si faltan algunas
  típicas (p.ej., 'entry_price', 'ret_20d_vol'), las crea con
  valores por defecto y lo informa por consola.
- Aplica gate por |y_hat| >= --min-abs-y y, opcionalmente, por
  probabilidad con --min-prob si existe 'prob_win'.
- Soporta --force-top-n para generar señales en los N mayores |y_hat|.
- Guarda CSV con las columnas originales + y_hat + prob_win (si procede)
  + signal.
- Imprime un pequeño JSON resumen al final.

Uso:
  python scripts/infer_and_gate.py \
    --features-csv reports/forecast/2025-10/features_labeled.csv \
    --out-csv reports/forecast/2025-10/forecast_2025-10_with_gate.csv \
    --model models/return_model_H3.joblib \
    --min-abs-y 0.06 \
    [--prob-model models/prob_win_clean.joblib] \
    [--min-prob 0.55] \
    [--force-top-n 5]
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------
DEFAULT_REQUIRED_COLS = {
    # columnas que con frecuencia exige el ColumnTransformer del pipeline
    "entry_price": 0.0,
    "ret_20d_vol": 0.0,
}

OPTIONAL_GATE_COLS = {
    # si tu flujo downstream espera estas columnas, las creamos vacías
    "tp": np.nan,
    "sl": np.nan,
    "rrr_abs": np.nan,
    "ticker": np.nan,
    "reason": "",
}


def _warn_created(prefix: str, created: list[str]) -> None:
    if created:
        print(f"⚠️  ({prefix}) Se crearon columnas faltantes: {created}")


def ensure_columns(df: pd.DataFrame,
                   required: dict[str, object],
                   prefix: str = "infer") -> pd.DataFrame:
    """Crea columnas faltantes con valores por defecto, avisando por consola."""
    created = []
    for col, val in required.items():
        if col not in df.columns:
            df[col] = val
            created.append(col)
    _warn_created(prefix, created)
    return df


def _align_X_for_model(df: pd.DataFrame, mdl) -> pd.DataFrame:
    """
    Intenta alinear X con lo que espera el pipeline de sklearn.
    Estrategia:
      - Si el pipeline tiene ColumnTransformer, confiamos en nombres de columnas
        y dejamos que lance error si realmente faltan.
      - Por robustez, devolvemos df tal cual (sin forzar solo numéricos),
        porque los pipelines suelen referirse a columnas por nombre.
    """
    return df


def _safe_predict_reg(mdl, X: pd.DataFrame) -> np.ndarray:
    """Predicción robusta para regresión."""
    return mdl.predict(X)


def _load_model(path: Path):
    try:
        mdl = joblib.load(path)
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar el modelo: {path} -> {e}")
    return mdl


def add_yhat(df: pd.DataFrame, model_path: Path) -> pd.DataFrame:
    """Añade columna y_hat usando modelo de regresión."""
    mdl = _load_model(model_path)

    # Asegurar columnas típicas que a veces faltan
    df = ensure_columns(df, DEFAULT_REQUIRED_COLS, prefix="pred")

    # X: intenta alinear con el pipeline
    X = _align_X_for_model(df, mdl)
    # Predecir
    try:
        yhat = _safe_predict_reg(mdl, X)
    except Exception as e:
        raise RuntimeError(f"Predicción y_hat falló: {e}")
    df = df.copy()
    df["y_hat"] = yhat
    return df


def add_prob(df: pd.DataFrame, prob_model_path: Path, prob_col: str = "prob_win") -> pd.DataFrame:
    """Añade columna de probabilidad (prob_win) si hay modelo; filtra a numéricos."""
    if prob_model_path is None:
        return df

    mdl = None
    try:
        mdl = joblib.load(prob_model_path)
    except Exception as e:
        print(f"ℹ️  No se pudo cargar modelo de probas ({prob_model_path}): {e}")
        return df

    # algunos artefactos antiguos pueden ser dicts, evitamos reventar
    if not hasattr(mdl, "predict") and not hasattr(mdl, "predict_proba"):
        print("ℹ️  Modelo de probas no es un estimador sklearn. Se omite prob_win.")
        return df

    # Asegurar columnas típicas para que el pipeline no truene de entrada
    df = ensure_columns(df, DEFAULT_REQUIRED_COLS, prefix="infer")

    # Alinear y FILTRAR a numéricos (clave para evitar '<' entre float/str)
    X = _align_X_for_model(df, mdl)
    X = X.select_dtypes(include=[np.number]).copy()

    try:
        if hasattr(mdl, "predict_proba"):
            p = mdl.predict_proba(X)
            # Si es binario, p[:,1]; si multiclass, prob de la clase positiva '1' si existe
            if p.ndim == 2 and p.shape[1] >= 2:
                prob = p[:, 1]
            else:
                prob = p.ravel()
        else:
            # algunos clasificadores regresan "score" directamente
            prob = mdl.predict(X)
        df = df.copy()
        df[prob_col] = pd.to_numeric(prob, errors="coerce")
    except Exception as e:
        print(f"ℹ️  Predicción de prob_win falló ({e}); se omite prob_win.")
    return df


def apply_gate(df: pd.DataFrame,
               min_abs_y: float = 0.0,
               min_prob: float | None = None,
               force_top_n: int = 0) -> pd.DataFrame:
    """
    Gate robusto por magnitud de y_hat y, opcionalmente, prob_win.
    Si force_top_n > 0, ignora umbrales y activa señales en los N mayores |y_hat|.
    """
    out = df.copy()

    # Asegurar columnas esperadas aguas abajo (por si tu flujo las requiere)
    out = ensure_columns(out, OPTIONAL_GATE_COLS, prefix="infer")

    # y_hat a numérico
    out["y_hat"] = pd.to_numeric(out.get("y_hat", np.nan), errors="coerce")

    # Señal por magnitud de y_hat
    out["signal"] = 0
    mask_mag = out["y_hat"].abs() >= float(min_abs_y)
    out.loc[mask_mag & (out["y_hat"] > 0), "signal"] = 1
    out.loc[mask_mag & (out["y_hat"] < 0), "signal"] = -1

    # Gate adicional por prob_win si se indicó y existe la columna
    if (min_prob is not None) and ("prob_win" in out.columns):
        out["prob_win"] = pd.to_numeric(out["prob_win"], errors="coerce")
        out.loc[out["prob_win"] < float(min_prob), "signal"] = 0

    # Forzar top-N por |y_hat| si se pide (debug / pruebas)
    if force_top_n and int(force_top_n) > 0:
        out["rank_abs"] = out["y_hat"].abs().rank(method="first", ascending=False)
        out["signal"] = 0
        out.loc[out["rank_abs"] <= int(force_top_n), "signal"] = np.where(out["y_hat"] >= 0, 1, -1)
        out.drop(columns=["rank_abs"], inplace=True, errors="ignore")
        print(f"[gate] force-top-n activado -> N={force_top_n}")

    # Limpiar tipo (evitar '0.0' o cadenas)
    out["signal"] = pd.to_numeric(out["signal"], errors="coerce").fillna(0).astype(int)

    # Log útil
    n_total = len(out)
    n_nonzero = int((out["signal"] != 0).sum())
    n_nan_y = int(out["y_hat"].isna().sum())
    print(f"[gate] total={n_total}  nonzero={n_nonzero}  nan_yhat={n_nan_y}  "
          f"thr_abs={min_abs_y}  thr_prob={min_prob}")

    return out


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-csv", required=True, help="CSV de entrada (features o labeled).")
    ap.add_argument("--out-csv", required=True, help="CSV de salida con y_hat, prob_win y signal.")
    ap.add_argument("--model", required=True, help="Modelo de regresión (joblib) para y_hat.")
    ap.add_argument("--prob-model", default=None, help="Modelo de probas (joblib) para prob_win (opcional).")
    ap.add_argument("--min-abs-y", type=float, default=0.0, help="Umbral de |y_hat| para activar señal.")
    ap.add_argument("--min-prob", type=float, default=None, help="Umbral mínimo de prob_win (opcional).")
    ap.add_argument("--force-top-n", type=int, default=0, help="Si >0, activa señales en los N con mayor |y_hat|.")
    return ap.parse_args()


def main():
    args = parse_args()

    inp = Path(args.features_csv)
    outp = Path(args.out_csv)
    outp.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(inp)

    # Inferencia de y_hat
    df = add_yhat(df, Path(args.model))

    # Probas (opcional)
    prob_model_path = Path(args.prob_model) if args.prob_model else None
    if prob_model_path:
        df = add_prob(df, prob_model_path, prob_col="prob_win")
    else:
        # Alinear API: deja constancia de que no hay probas
        df["prob_win"] = np.nan

    # Gate
    df = apply_gate(
        df,
        min_abs_y=float(args.min_abs_y or 0.0),
        min_prob=(float(args.min_prob) if args.min_prob is not None else None),
        force_top_n=int(args.force_top_n or 0),
    )

    # Guardar
    df.to_csv(outp, index=False)
    has_prob = "prob_win" in df.columns
    summary = {
        "rows": int(len(df)),
        "min_abs_y": float(args.min_abs_y or 0.0),
        "min_prob": (float(args.min_prob) if args.min_prob is not None else None),
        "has_prob": bool(has_prob),
        "outfile": str(outp).replace("/", "\\"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
