import pandas as pd
import yfinance as yf
from datetime import datetime
import os
import yaml

BUFFER_PATH = "data/intraday5/buffer/"
CONFIG_PATH = "config/data_sources.yaml"


def load_tickers():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config['tickers']


def download_intraday_5m(ticker, start_date, end_date):
    df = yf.download(ticker, start=start_date, end=end_date, interval="5m", auto_adjust=True, progress=False)
    if df.empty:
        return None
    df = df.reset_index()
    df['ticker'] = ticker
    df = df.rename(columns={
        'Datetime': 'timestamp',
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.drop_duplicates(subset=['timestamp'])
    df = df.sort_values('timestamp')
    return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ticker']]


def save_to_buffer(df, ticker, date):
    os.makedirs(BUFFER_PATH, exist_ok=True)
    fname = f"{BUFFER_PATH}{ticker}_{date}.parquet"
    df.to_parquet(fname, index=False, compression='snappy')
    print(f"[OK] Guardado {fname} ({len(df)} filas)")


def main():
    tickers = load_tickers()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for ticker in tickers:
        print(f"Descargando {ticker} 5m...")
        df = download_intraday_5m(ticker, today, today)
        if df is not None and len(df) > 0:
            save_to_buffer(df, ticker, today)
        else:
            print(f"[WARN] Sin datos para {ticker}")

if __name__ == "__main__":
    main()
