# =============================================
# 1. download_us_prices.py
# =============================================
# Descarga precios OHLCV diarios desde Yahoo Finance
# y guarda en data/us/ohlcv_us_daily.csv

import yfinance as yf
import pandas as pd
import argparse, os
from datetime import date

def download_prices(tickers, start="2020-01-01", end=None):
    data = yf.download(tickers, start=start, end=end, group_by='ticker', auto_adjust=True)
    rows = []
    for t in tickers:
        if t not in data.columns.levels[0]:
            continue
        df_t = data[t].copy()
        df_t['ticker'] = t
        df_t = df_t.rename(columns={'Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'})
        rows.append(df_t.reset_index())
    df_all = pd.concat(rows, ignore_index=True)
    df_all['Date'] = pd.to_datetime(df_all['Date'])
    df_all = df_all.rename(columns={'Date':'date'})
    return df_all[['date','ticker','open','high','low','close','volume']]

def get_tickers_today():
    rot_path = "data/us/tickers_rotation.csv"
    master_path = "data/us/tickers_master.csv"
    if os.path.exists(rot_path):
        rot = pd.read_csv(rot_path)
        wk = date.today().isocalendar().week
        yr = date.today().year
        week_str = f"{yr}-W{wk:02d}"
        row = rot[rot['week'].str.strip() == week_str]
        if not row.empty:
            file = row.iloc[0]['tickers_file']
            if os.path.exists(file):
                return pd.read_csv(file)['ticker'].tolist()
    # fallback: master
    if os.path.exists(master_path):
        return pd.read_csv(master_path)['ticker'].tolist()
    # fallback: default
    return ["AAPL","MSFT","NVDA","TSLA","AMZN","JPM","SPY"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="", help="Lista explícita de tickers separados por coma (tiene prioridad)")
    ap.add_argument("--universe", default="rotation", choices=["rotation","master","file"], help="Origen de universo de tickers cuando no se pasa --tickers")
    ap.add_argument("--tickers-file", default="", help="CSV con columna 'ticker' cuando --universe=file")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--out", default="data/us/ohlcv_us_daily.csv")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        if args.universe == "master":
            master_path = "data/us/tickers_master.csv"
            if not os.path.exists(master_path):
                raise SystemExit(f"No existe {master_path}")
            tickers = pd.read_csv(master_path)['ticker'].dropna().astype(str).str.strip().tolist()
        elif args.universe == "file":
            if not args.tickers_file or not os.path.exists(args.tickers_file):
                raise SystemExit("Debe proporcionar --tickers-file válido cuando --universe=file")
            tickers = pd.read_csv(args.tickers_file)['ticker'].dropna().astype(str).str.strip().tolist()
        else:
            tickers = get_tickers_today()
    df = download_prices(tickers, start=args.start)
    df.to_csv(args.out, index=False)
    print(f"[download] Guardado {args.out} ({len(df)} filas, {len(tickers)} tickers)")

if __name__ == "__main__":
    main()
