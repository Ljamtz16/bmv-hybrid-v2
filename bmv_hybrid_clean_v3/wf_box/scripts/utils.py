
import os, json, hashlib, pandas as pd, numpy as np
from pathlib import Path

def sha256_file(path, chunk=65536):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)

def month_bounds(ym):
    y, m = map(int, ym.split("-"))
    start = pd.Timestamp(y, m, 1)
    end = (start + pd.offsets.MonthEnd(1))
    return start, end

def add_basic_features(df, cfg_feat):
    df = df.copy()
    df["log_ret"] = np.log(df["Close"]).diff()
    for w in cfg_feat.get("ma_windows", [5,10,20]):
        df[f"ma_{w}"] = df["Close"].rolling(w).mean()
        df[f"ret_ma_{w}"] = df["log_ret"].rolling(w).sum()
    volw = cfg_feat.get("vol_window", 10)
    df["vol_"+str(volw)] = df["log_ret"].rolling(volw).std().fillna(0.0)
    df = df.dropna().reset_index(drop=True)
    return df

def add_target(df, horizon=5):
    df = df.copy()
    df["log_ret"] = np.log(df["Close"]).diff()
    df["y_true"] = df["log_ret"].shift(-1).rolling(horizon).sum()
    return df
