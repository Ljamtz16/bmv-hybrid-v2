# scripts/03_build_features_1h.py
from pathlib import Path
import pandas as pd
import numpy as np
import os

def add_features_1h(df):
    # Ejemplo de features horarios
    if "close" in df.columns:
        df["momentum_5h"] = df["close"] - df["close"].shift(5)
        df["vol_20h"] = df["close"].rolling(20).std()
    if "high" in df.columns and "low" in df.columns:
        df["range_intraday"] = df["high"] - df["low"]
        df["spread"] = (df["high"] - df["low"]) / df["close"]
    if "open" in df.columns and "close" in df.columns:
        df["gap"] = df["open"] - df["close"].shift(1)
    return df

def main():
    raw_dir = Path("data/raw/1h")
    out_dir = Path("data/interim")
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in raw_dir.glob("*_1h.csv"):
        df = pd.read_csv(f)
        df_feat = add_features_1h(df)
        out_path = out_dir / f.name.replace(".csv", "_features.csv").replace(".MX_1h", "_MX_1h")
        df_feat.to_csv(out_path, index=False)
        print(f"✅ Features 1h guardados en {out_path}")

if __name__ == "__main__":
    main()
