import pandas as pd
import os
import glob

BUFFER_PATH = "data/intraday5/buffer/"
HISTORY_PATH = "data/intraday5/history/"


def rollup_buffer_to_history():
    files = glob.glob(BUFFER_PATH + "*.parquet")
    if not files:
        print("[WARN] No hay archivos en buffer.")
        return
    for f in files:
        df = pd.read_parquet(f)
        if df.empty:
            continue
        ticker = df['ticker'].iloc[0]
        date = pd.to_datetime(df['timestamp'].iloc[0]).strftime("%Y-%m-%d")
        out_dir = f"{HISTORY_PATH}ticker={ticker}/date={date}/"
        os.makedirs(out_dir, exist_ok=True)
        out_file = f"{out_dir}part-0.parquet"
        # Deduplicar y ordenar
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.sort_values('timestamp')
        df.to_parquet(out_file, index=False, compression='snappy')
        print(f"[OK] Rollup {f} → {out_file} ({len(df)} filas)")
        os.remove(f)

if __name__ == "__main__":
    rollup_buffer_to_history()
