# =============================================
# 30_validate_intraday_hits.py
# =============================================
# Lee simulate_results_merged.csv o simulate_results.csv de un mes,
# descarga (o reutiliza) intradía por trade y valida si el TP/SL se habría activado intradía.

import argparse, os, math
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

import yfinance as yf


def _to_cdmx_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    idx = df.index
    try:
        if idx.tz is None:
            df.index = idx.tz_localize("UTC").tz_convert("America/Mexico_City")
        else:
            df.index = idx.tz_convert("America/Mexico_City")
    except Exception:
        pass
    return df


def ensure_intraday(ticker: str, start_date: str, end_date: str, interval: str, outdir: str) -> str:
    os.makedirs(os.path.join(outdir, ticker), exist_ok=True)
    out = os.path.join(outdir, ticker, f"{ticker}_{start_date}_{end_date}_{interval}.csv")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    # download
    df = yf.download(ticker, start=start_date, end=end_date, interval=interval, progress=False)
    if df is None or df.empty:
        pd.DataFrame().to_csv(out, index=False)
        return out
    df = _to_cdmx_index(df)
    df.to_csv(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--dir", default="reports/forecast")
    ap.add_argument("--intraday-dir", default="data/us/intraday")
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--lookahead-days", type=int, default=5)
    ap.add_argument("--in-file", default="simulate_results_merged.csv")
    ap.add_argument("--out-file", default="intraday_validation.csv")
    args = ap.parse_args()

    base = os.path.join(args.dir, args.month)
    in_path = os.path.join(base, args.in_file)
    if not os.path.exists(in_path):
        # fallback
        in_path = os.path.join(base, "simulate_results.csv")
    if not os.path.exists(in_path):
        raise SystemExit(f"No existe simulate results en {base}")

    trades = pd.read_csv(in_path)
    trades.columns = [c.strip().lower() for c in trades.columns]
    # columnas necesarias
    need = ["ticker","entry_date","tp_pct_suggested","sl_pct_suggested","entry_price"]
    for c in need:
        if c not in trades.columns:
            trades[c] = np.nan

    # Normalizar fechas
    trades["entry_dt"] = pd.to_datetime(trades["entry_date"], errors="coerce")

    rows = []
    for _, r in trades.iterrows():
        t = str(r.get("ticker"))
        if not t or t == 'nan':
            continue
        entry_dt = r.get("entry_dt")
        if pd.isna(entry_dt):
            continue
        start_date = entry_dt.date().isoformat()
        end_date = (entry_dt + timedelta(days=args.lookahead_days)).date().isoformat()
        path = ensure_intraday(t, start_date, end_date, args.interval, args.intraday_dir)
        try:
            # Leer con índice de tiempo y parsear fechas
            idf = pd.read_csv(path, index_col=0, parse_dates=True)
            # Normalizar columnas OHLCV
            idf.columns = [c.strip().lower() for c in idf.columns]
            if 'high' not in idf.columns and 'High' in idf.columns:
                idf.rename(columns={'High':'high'}, inplace=True)
            if 'low' not in idf.columns and 'Low' in idf.columns:
                idf.rename(columns={'Low':'low'}, inplace=True)
            if 'open' not in idf.columns and 'Open' in idf.columns:
                idf.rename(columns={'Open':'open'}, inplace=True)
            if 'close' not in idf.columns and 'Close' in idf.columns:
                idf.rename(columns={'Close':'close'}, inplace=True)
        except Exception:
            idf = pd.DataFrame()

        entry_price = r.get("entry_price")
        tp_pct = r.get("tp_pct_suggested", np.nan)
        sl_pct = r.get("sl_pct_suggested", np.nan)
        tp_hit = False
        sl_hit = False
        tp_ts = None
        sl_ts = None
        tp_price = None
        sl_price = None
        try:
            if pd.notna(entry_price) and pd.notna(tp_pct):
                tp_price = float(entry_price) * (1.0 + float(tp_pct))
            if pd.notna(entry_price) and pd.notna(sl_pct):
                sl_price = float(entry_price) * (1.0 - float(sl_pct))
        except Exception:
            pass

        if not idf.empty and (tp_price is not None or sl_price is not None):
            # buscar primera vela donde se alcanza TP o SL
            for ts, ir in idf.iterrows():
                hi = ir.get('high'); lo = ir.get('low')
                if tp_price is not None and hi is not None and not pd.isna(hi) and hi >= tp_price and not tp_hit:
                    tp_hit = True
                    tp_ts = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                if sl_price is not None and lo is not None and not pd.isna(lo) and lo <= sl_price and not sl_hit:
                    sl_hit = True
                    sl_ts = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                if tp_hit or sl_hit:
                    break

        rows.append({
            'ticker': t,
            'entry_date': start_date,
            'interval': args.interval,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'tp_hit_intraday': bool(tp_hit),
            'sl_hit_intraday': bool(sl_hit),
            'tp_ts': tp_ts,
            'sl_ts': sl_ts,
            'intraday_file': path
        })

    out_path = os.path.join(base, args.out_file)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"[intraday] Validación guardada -> {out_path} (rows={len(rows)})")


if __name__ == "__main__":
    main()
