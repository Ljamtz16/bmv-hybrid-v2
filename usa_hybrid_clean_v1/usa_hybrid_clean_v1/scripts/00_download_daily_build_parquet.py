# Rebuild wide/long daily parquet from authoritative CSV (ohlcv_us_daily.csv)
# Output is long format (date,ticker,open,high,low,close,volume) for robustness.
# 09_make_features_daily.py was updated to accept long format directly.

import sys
import pandas as pd
from pathlib import Path


def enable_utf8_output():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            import io as _io
            sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

CSV = Path("data/us/ohlcv_us_daily.csv")
PARQ = Path("data/daily/ohlcv_daily.parquet")


def main():
    enable_utf8_output()
    if not CSV.exists():
        raise SystemExit(f"Missing CSV: {CSV}")
    df = pd.read_csv(CSV)
    # Normalize types
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    # Order and drop duplicates
    df = df.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    PARQ.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQ, index=False)
    print(f"[OK] parquet rebuilt from CSV → {PARQ} | rows={len(df)} | max_date={df['date'].max()}")


if __name__ == "__main__":
    main()
