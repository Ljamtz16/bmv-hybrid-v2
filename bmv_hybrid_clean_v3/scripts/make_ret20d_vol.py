#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcula ret_20d_vol a partir de precios diarios y lo inserta en tu CSV de features.
- Lee: data/daily/ohlcv_daily.csv (requiere 'date','ticker' y 'Close' o 'Adj Close')
- Fusiona ret_20d_vol a reports/forecast/latest_forecast_features.csv (ajusta la ruta si usas otra)
- Soporta el caso donde ya existe ret_20d_vol en features (coalesce entre la existente y la nueva)
"""

from pathlib import Path
import numpy as np
import pandas as pd

PRICES_CSV   = Path("data/daily/ohlcv_daily.csv")
FEATURES_CSV = Path("reports/forecast/latest_forecast_features.csv")  # cambia si trabajas por mes

def to_naive_date(s):
    # Fecha calendario sin tz
    d = pd.to_datetime(s, errors="coerce", utc=True).dt.date
    return pd.to_datetime(d, errors="coerce")

def main():
    # --- Precios ---
    p = pd.read_csv(PRICES_CSV)
    if "ticker" not in p.columns or "date" not in p.columns:
        raise ValueError("ohlcv_daily.csv debe tener columnas 'ticker' y 'date'.")
    ccol = "Close" if "Close" in p.columns else ("Adj Close" if "Adj Close" in p.columns else None)
    if ccol is None:
        raise ValueError("ohlcv_daily.csv no tiene 'Close' ni 'Adj Close'.")
    p["date"] = to_naive_date(p["date"])
    p = p[["date","ticker", ccol]].rename(columns={ccol:"Close"}).dropna().sort_values(["ticker","date"])

    # Retorno 1d y vol 20d anualizada aprox
    p["ret1d"] = p.groupby("ticker")["Close"].pct_change()
    p["ret_20d_vol_new"] = p.groupby("ticker")["ret1d"].rolling(20).std().reset_index(level=0, drop=True) * np.sqrt(252)
    vol = p[["date","ticker","ret_20d_vol_new"]]

    # --- Features ---
    f = pd.read_csv(FEATURES_CSV)
    if "ticker" not in f.columns or "date" not in f.columns:
        raise ValueError("El CSV de features debe tener columnas 'ticker' y 'date'.")
    f["date"] = to_naive_date(f["date"])

    # Si ya existe ret_20d_vol en features, la preservamos como *_feat
    existed = "ret_20d_vol" in f.columns
    if existed:
        f = f.rename(columns={"ret_20d_vol": "ret_20d_vol_feat"})

    # Merge
    f2 = f.merge(vol, on=["ticker","date"], how="left")

    # Coalesce para dejar SIEMPRE 'ret_20d_vol'
    if existed:
        # preferimos la nueva si existe; si no, la de features
        f2["ret_20d_vol"] = f2["ret_20d_vol_new"].where(f2["ret_20d_vol_new"].notna(), f2["ret_20d_vol_feat"])
        f2 = f2.drop(columns=[c for c in ["ret_20d_vol_new","ret_20d_vol_feat"] if c in f2.columns])
    else:
        # si no existía, basta con renombrar la nueva a ret_20d_vol
        f2 = f2.rename(columns={"ret_20d_vol_new": "ret_20d_vol"})
        # si por alguna razón no quedó creada, la generamos vacía
        if "ret_20d_vol" not in f2.columns:
            f2["ret_20d_vol"] = np.nan

    # Guardar
    f2.to_csv(FEATURES_CSV, index=False)
    miss = int(f2["ret_20d_vol"].isna().sum())
    print(f"✅ ret_20d_vol añadido/actualizado en {FEATURES_CSV} (rows={len(f2)}, faltantes={miss})")

if __name__ == "__main__":
    main()
