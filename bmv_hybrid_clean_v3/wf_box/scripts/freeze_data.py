
import os, json, yaml, pandas as pd
from pathlib import Path
from utils import sha256_file, ensure_dir

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
RAW = os.path.join(ROOT, "data", "raw")
FROZEN = os.path.join(ROOT, "data", "frozen")

def sha256_file(path, chunk=65536):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def main():
    with open(os.path.join(ROOT, "manifest.yaml"), "r", encoding="utf-8") as f:
        man = yaml.safe_load(f)

    uni = man["universe"]
    start = pd.to_datetime(man["date_range"]["start"])
    end = pd.to_datetime(man["date_range"]["end"])

    lock = {"files": [], "range": {"start": str(start.date()), "end": str(end.date())}}

    for t in uni:
        src = os.path.join(RAW, f"{t}.csv")
        if not os.path.exists(src):
            raise FileNotFoundError(f"Falta CSV: {src}")
        h = sha256_file(src)
        df = pd.read_csv(src, parse_dates=["Date"])
        df = df.sort_values("Date")
        df = df[(df["Date"]>=start) & (df["Date"]<=end)]
        required = ["Date","Open","High","Low","Close","Volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"{t}: faltan columnas {missing}")
        dst = os.path.join(FROZEN, f"{t}.parquet")
        df.to_parquet(dst, index=False)
        lock["files"].append({"ticker": t, "src": src, "hash": h, "rows": int(len(df))})

    with open(os.path.join(FROZEN, "DATASET_LOCK.json"), "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)
    print("Freeze listo. Archivos:", len(lock["files"]))

if __name__ == "__main__":
    main()
