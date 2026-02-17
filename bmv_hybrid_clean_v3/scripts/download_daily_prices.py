#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Downloader robusto de OHLCV diario con yfinance.

Objetivos:
- Leer tickers y rango de fechas desde un CSV de features (col: 'ticker','date').
- Descargar OHLCV 1d para cada ticker y normalizar columnas.
- Asegurar que el CSV final tenga al menos: ['date','ticker','Close'].
- Extender el rango hacia adelante: H (horizon-days) + margin-bdays (días hábiles)
  para que existan forward labels (Close_fwd_H{H}) y targets (y_H{H}).

Uso:
  python scripts/download_daily_prices.py \
      --features-csv reports/forecast/latest_forecast_features.csv \
      --out-csv data/daily/ohlcv_daily.csv \
      --horizon-days 3 \
      --margin-bdays 10

Notas:
- Si 'Close' no existe pero hay 'Adj Close', se usa como 'Close'.
- Se toleran variaciones de nombres de columnas (Open/High/Low/Close/Adj Close/Volume).
- Maneja reintentos y normaliza fechas a naive (fecha calendario).
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------
# Helpers de fecha
# ---------------------------------------------------------------------
def to_naive_date(s):
    """Convierte a fecha calendario sin tz (datetime naive a medianoche)."""
    d = pd.to_datetime(s, errors="coerce", utc=True).dt.date
    return pd.to_datetime(d, errors="coerce")

# ---------------------------------------------------------------------
# Lectura de tickers y rango desde features
# ---------------------------------------------------------------------
def read_features_tickers(features_csv: Path):
    usecols = None
    try:
        # Cargamos solo las columnas necesarias si existen
        probe = pd.read_csv(features_csv, nrows=0)
        cols = list(probe.columns)
        if "ticker" not in cols or "date" not in cols:
            raise ValueError("El CSV de features debe tener columnas 'ticker' y 'date'.")
        usecols = ["ticker", "date"]
    except Exception:
        # Si falla la lectura parcial, leemos completo
        pass

    df = pd.read_csv(features_csv, usecols=usecols)
    if "ticker" not in df.columns or "date" not in df.columns:
        raise ValueError("El CSV de features debe tener columnas 'ticker' y 'date'.")

    df["date"] = to_naive_date(df["date"])
    dmin, dmax = df["date"].min(), df["date"].max()
    tickers = sorted(
        t for t in df["ticker"].dropna().astype(str).map(str.strip).unique() if t
    )
    return tickers, dmin, dmax

# ---------------------------------------------------------------------
# Normalización de columnas OHLCV
# ---------------------------------------------------------------------
CANON_KEEP = ["date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]

def _canon_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Mapea nombres a forma canónica, case-insensitive."""
    low2orig = {c.lower(): c for c in df.columns}
    ren = {}
    if "date" in low2orig:      ren[low2orig["date"]] = "date"
    if "datetime" in low2orig:  ren[low2orig["datetime"]] = "date"
    if "timestamp" in low2orig: ren[low2orig["timestamp"]] = "date"
    if "open" in low2orig:      ren[low2orig["open"]] = "Open"
    if "high" in low2orig:      ren[low2orig["high"]] = "High"
    if "low" in low2orig:       ren[low2orig["low"]] = "Low"
    if "close" in low2orig:     ren[low2orig["close"]] = "Close"
    if "adj close" in low2orig: ren[low2orig["adj close"]] = "Adj Close"
    if "adjclose" in low2orig:  ren[low2orig["adjclose"]] = "Adj Close"
    if "volume" in low2orig:    ren[low2orig["volume"]] = "Volume"
    return df.rename(columns=ren)

# ---------------------------------------------------------------------
# Descarga por ticker con reintentos
# ---------------------------------------------------------------------
def fetch_one(ticker: str, start: str, end: str, max_retries: int = 3, sleep_s: float = 0.6) -> pd.DataFrame | None:
    import yfinance as yf

    for _ in range(max_retries):
        try:
            hist = yf.Ticker(ticker).history(
                start=start, end=end, interval="1d", auto_adjust=False
            )
            if hist is None or hist.empty:
                time.sleep(sleep_s)
                continue

            df = hist.reset_index().copy()
            # Normaliza columnas
            df = _canon_cols(df)

            # Asegurar 'date'
            if "date" not in df.columns:
                # A veces 'Date' queda como índice tras reset_index mal aplicado
                if df.index.name in ("Date", "date"):
                    df = df.reset_index().rename(columns={df.index.name: "date"})
            if "date" not in df.columns:
                time.sleep(sleep_s)
                continue

            # Si no hay Close pero hay Adj Close, úsala como Close
            if "Close" not in df.columns and "Adj Close" in df.columns:
                df["Close"] = df["Adj Close"]

            # Si aún no hay Close, descarta
            if "Close" not in df.columns:
                time.sleep(sleep_s)
                continue

            # Filtrar y ordenar
            keep = [c for c in CANON_KEEP if c in df.columns]
            df = df[keep].copy()
            # Normalizar fecha a naive
            df["date"] = to_naive_date(df["date"])
            df = df.dropna(subset=["date"]).sort_values("date")
            # Añadir ticker
            df["ticker"] = ticker
            # Reordenar columnas
            cols = ["date", "ticker"] + [c for c in CANON_KEEP if c in df.columns and c not in ("date")]
            df = df[cols]
            return df

        except Exception:
            time.sleep(sleep_s)

    return None

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-csv", required=True, help="CSV de features (lee 'ticker' y 'date' para rango)")
    ap.add_argument("--tickers", nargs="*", default=None, help="Lista manual de tickers (opcional; se une a los detectados)")
    ap.add_argument("--out-csv", default="data/daily/ohlcv_daily.csv", help="Archivo de salida OHLCV")
    ap.add_argument("--horizon-days", type=int, default=5, help="H dias de horizonte futuro a cubrir")
    ap.add_argument("--margin-bdays", type=int, default=10, help="margen extra de dias habiles por delante")
    ap.add_argument("--backpad-days", type=int, default=40, help="dias calendario a restar antes del minimo de features")
    ap.add_argument("--retries", type=int, default=3, help="reintentos por ticker")
    args = ap.parse_args()

    outp = Path(args.out_csv)
    outp.parent.mkdir(parents=True, exist_ok=True)

    # 1) Tickers y rango desde features
    tks, dmin, dmax = read_features_tickers(Path(args.features_csv))
    if args.tickers:
        tks = sorted(set(tks).union(set(map(str, args.tickers))))
    if not tks:
        print("No se detectaron tickers en features ni por argumento.", file=sys.stderr)
        sys.exit(1)

    # 2) Rango de descarga
    #    - hacia atrás: backpad-days
    #    - hacia adelante: H + margin-bdays en días hábiles
    from pandas.tseries.offsets import BDay
    start_dt = pd.to_datetime(dmin) - pd.Timedelta(days=int(args.backpad_days))
    end_dt = pd.to_datetime(dmax) + BDay(int(args.horizon_days) + int(args.margin_bdays))
    start = start_dt.date().isoformat()
    end = end_dt.date().isoformat()

    # 3) Descarga por ticker
    frames, skipped = [], []
    for t in tks:
        df = fetch_one(t, start, end, max_retries=args.retries)
        if df is None or df.empty or "Close" not in df.columns:
            skipped.append(t)
            continue
        frames.append(df)

    if not frames:
        print("Descarga vacia: ningun ticker con columnas de precio validas.", file=sys.stderr)
        if skipped:
            print("Tickers problematicos (sin Close): " + ", ".join(skipped[:20]), file=sys.stderr)
        sys.exit(2)

    # 4) Concatenar y guardar
    out_df = pd.concat(frames, ignore_index=True)
    # Orden y tipos
    out_df = out_df.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Guardar
    out_df.to_csv(outp, index=False)

    # 5) Resumen
    ntickers = out_df["ticker"].nunique()
    nrows = len(out_df)
    print(f"✅ OHLCV guardado en: {outp} (rows={nrows}, tickers={ntickers})")
    if skipped:
        print(f"⚠️ Sin datos validos para {len(skipped)} ticker(s): {', '.join(skipped[:10])}" + (" ..." if len(skipped) > 10 else ""))

if __name__ == "__main__":
    main()
