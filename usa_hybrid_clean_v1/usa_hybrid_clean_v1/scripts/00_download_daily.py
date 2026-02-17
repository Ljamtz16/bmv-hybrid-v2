# Script: 00_download_daily.py
# Descarga y guarda datos OHLCV diarios en Parquet unificado (UTC, schema estándar)
import pandas as pd
import yfinance as yf
from datetime import datetime
import os
import yaml

OUTPUT_PATH = "data/daily/ohlcv_daily.parquet"
CONFIG_PATH = "config/data_sources.yaml"


def load_tickers():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config['tickers']


def download_daily_ohlcv(tickers, start_date, end_date):
    all_data = []
    for ticker in tickers:
        print(f"Descargando {ticker}...")
        df = yf.download(ticker, start=start_date, end=end_date, interval="1d", auto_adjust=True, progress=False)
        if df.empty:
            continue
        df = df.reset_index()
        df['ticker'] = ticker
        df = df.rename(columns={
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        all_data.append(df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ticker']])
    if all_data:
        df_all = pd.concat(all_data).sort_values(['ticker', 'timestamp'])
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        df_all.to_parquet(OUTPUT_PATH, index=False, compression='snappy')
        print(f"[OK] Guardado {len(df_all)} filas en {OUTPUT_PATH}")
    else:
        print("[WARN] No se descargaron datos.")

if __name__ == "__main__":
    tickers = load_tickers()
    download_daily_ohlcv(tickers, "2023-01-01", datetime.today().strftime("%Y-%m-%d"))
