import pandas as pd
import os
import glob
from datetime import datetime, timedelta

HISTORY_5M = "data/intraday5/history/"
HISTORY_15M = "data/intraday15/history/"
ROLLING_DAYS = 180


def resample_5m_to_15m():
    tickers = [d for d in os.listdir(HISTORY_5M) if d.startswith("ticker=")]
    for ticker_dir in tickers:
        ticker = ticker_dir.split("=")[1]
        date_dirs = glob.glob(f"{HISTORY_5M}{ticker_dir}/date=*/")
        for date_dir in date_dirs:
            files = glob.glob(f"{date_dir}*.parquet")
            for f in files:
                df = pd.read_parquet(f)
                if df.empty:
                    continue
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                df = df.set_index('timestamp').sort_index()
                df_15m = df.resample('15T').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum',
                    'ticker': 'first'
                }).dropna().reset_index()
                out_dir = f"{HISTORY_15M}ticker={ticker}/date={df_15m['timestamp'].dt.strftime('%Y-%m-%d').iloc[0]}/"
                os.makedirs(out_dir, exist_ok=True)
                out_file = f"{out_dir}part-0.parquet"
                df_15m.to_parquet(out_file, index=False, compression='snappy')
                print(f"[OK] Resample {f} → {out_file} ({len(df_15m)} filas)")

def cleanup_old_15m():
    cutoff = datetime.utcnow() - timedelta(days=ROLLING_DAYS)
    for ticker_dir in glob.glob(f"{HISTORY_15M}ticker=*/"):
        for date_dir in glob.glob(f"{ticker_dir}date=*/"):
            date_str = date_dir.split("date=")[1].replace("/", "")
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if date_obj < cutoff:
                    for f in glob.glob(f"{date_dir}*.parquet"):
                        os.remove(f)
                    print(f"[CLEAN] Borrado {date_dir}")
            except Exception as e:
                print(f"[WARN] Fecha inválida en {date_dir}: {e}")

def main():
    resample_5m_to_15m()
    cleanup_old_15m()

if __name__ == "__main__":
    main()
