#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evalúa modelos de regresión (.pkl/.joblib) que predicen retorno (ej. H3/H5).
Genera métricas MAE, RMSE, R2 y guarda reg_metrics_*.json junto al modelo.
"""

import argparse, json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import matplotlib.pyplot as plt

def load_model(model_path: Path):
    mdl = joblib.load(model_path)
    return mdl

def compute_reg_metrics(y_true, y_pred):
    mae  = float(mean_absolute_error(y_true, y_pred))
    rmse = float(mean_squared_error(y_true, y_pred, squared=False))
    r2   = float(r2_score(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.where(y_true!=0, y_true, np.nan)))*100.0)
    return {"MAE": mae, "RMSE": rmse, "R2": r2, "MAPE_pct": mape}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Ruta al modelo .joblib/.pkl")
    ap.add_argument("--features-csv", required=True, help="Ruta al CSV con features y target real")
    ap.add_argument("--target", required=True, help="Nombre de la columna target (ej. y_H3)")
    ap.add_argument("--id-col", default=None, help="Columna identificador (ej. ticker)")
    ap.add_argument("--drop-cols", nargs="*", default=[], help="Columnas a eliminar (ids/leaks)")
    ap.add_argument("--outdir", default=None, help="Carpeta de salida (default: carpeta del modelo)")
    args = ap.parse_args()

    model_path = Path(args.model)
    outdir = Path(args.outdir) if args.outdir else model_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.features_csv)
    if args.target not in df.columns:
        raise ValueError(f"No se encontró la columna target '{args.target}'.")

    cols_to_drop = list(args.drop_cols)
    if args.id_col and args.id_col in df.columns:
        cols_to_drop.append(args.id-col)
    X = df.drop(columns=cols_to_drop + [args.target], errors="ignore")
    y = df[args.target].astype(float)

    model = load_model(model_path)
    y_pred = model.predict(X)
    metrics = compute_reg_metrics(y, y_pred)

    metrics_path = outdir / f"reg_metrics_{model_path.stem}.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("✅ Evaluación completada")
    print("📊", metrics)
    print(f"🧾 {metrics_path}")

    # Opcional: scatter plot y residuos
    fig1 = plt.figure(figsize=(4,4))
    plt.scatter(y, y_pred, alpha=0.6)
    plt.plot([y.min(), y.max()], [y.min(), y.max()], "r--")
    plt.xlabel("y_true")
    plt.ylabel("y_pred")
    plt.title("Predicción vs Real")
    fig1.savefig(outdir / f"reg_scatter_{model_path.stem}.png", dpi=160)
    plt.close(fig1)

if __name__ == "__main__":
    main()

