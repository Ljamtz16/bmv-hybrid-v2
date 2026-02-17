# =============================================
# 29_download_intraday.py
# =============================================
# Descarga OHLCV intradía desde Yahoo Finance para un ticker en un rango de fechas
# y guarda en CSV con conversión de zona horaria a America/Mexico_City.

import argparse, os
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf


def _parse_date(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # Intento flexible YYYY-MM-DD
        return pd.to_datetime(s).to_pydatetime()


def _to_cdmx_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    idx = df.index
    try:
        if idx.tz is None:
            # yfinance típicamente entrega UTC naive para intradía
            df.index = idx.tz_localize("UTC").tz_convert("America/Mexico_City")
        else:
            df.index = idx.tz_convert("America/Mexico_City")
    except Exception:
        # Como fallback, intentar sin conversión
        pass
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--start", required=True, help="Fecha inicio (YYYY-MM-DD o ISO)")
    ap.add_argument("--end", required=False, help="Fecha fin (YYYY-MM-DD o ISO)")
    ap.add_argument("--interval", default="15m", help="Intervalo intradía: 1m,2m,5m,15m,30m,60m,90m")
    ap.add_argument("--outdir", default="data/us/intraday")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    start_dt = _parse_date(args.start)
    if args.end:
        end_dt = _parse_date(args.end)
    else:
        end_dt = start_dt + timedelta(days=5)

    print(f"[intraday] Descargando {args.ticker} {args.interval} de {start_dt.date()} a {end_dt.date()}")
    df = yf.download(args.ticker, start=start_dt, end=end_dt, interval=args.interval, progress=False)
    if df is None or df.empty:
        out = os.path.join(args.outdir, f"{args.ticker}_{start_dt.date()}_{args.interval}_EMPTY.csv")
        pd.DataFrame().to_csv(out, index=False)
        print(f"[intraday] Sin datos -> {out}")
        return

    df = _to_cdmx_index(df)
    # Guardar por ticker subcarpeta
    tdir = os.path.join(args.outdir, args.ticker)
    os.makedirs(tdir, exist_ok=True)
    out = os.path.join(tdir, f"{args.ticker}_{start_dt.date()}_{end_dt.date()}_{args.interval}.csv")
    df.to_csv(out)
    print(f"[intraday] Guardado: {out} ({len(df)} filas)")


if __name__ == "__main__":
    main()
