# src/io/loader.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Iterable, Optional, List
import pandas as pd

CANON_ORDER = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]

# --------------------------------------------------------------------------------------
# Rutas compatibles (tolerantes):
#   A) data/raw/<freq>/{TICKER}.csv
#   B) data/raw/{TICKER}_{freq}.csv
#   C) data/raw/<freq>/{TICKER}_{freq}.csv
#   D) data/raw/{TICKER}.csv
# --------------------------------------------------------------------------------------
def _candidate_paths_for_ticker(base_raw_dir: Path, ticker: str, freq: str) -> List[Path]:
    return [
        base_raw_dir / freq / f"{ticker}.csv",          # A
        base_raw_dir / f"{ticker}_{freq}.csv",          # B
        base_raw_dir / freq / f"{ticker}_{freq}.csv",   # C
        base_raw_dir / f"{ticker}.csv",                 # D
    ]

def _read_csv_generic(p: Path) -> pd.DataFrame:
    # Lectura normal
    df = pd.read_csv(p)
    # Formato export de Yahoo con "Price/Ticker/Date" en primeras filas
    if "Price" in df.columns and not set(df.columns) & {"Open", "High", "Low", "Close"}:
        df = pd.read_csv(p, skiprows=2)
    return df

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        lvl0 = [c[0] for c in df.columns]
        if set(lvl0) & {"Open","High","Low","Close","Adj Close","Volume"}:
            df.columns = lvl0
        else:
            df.columns = [c[1] for c in df.columns]
    ren = {
        "open":"Open","high":"High","low":"Low","close":"Close",
        "adj close":"Adj Close","adj_close":"Adj Close","adjclose":"Adj Close",
        "volume":"Volume",
    }
    df = df.rename(columns={c: ren.get(str(c).lower(), c) for c in df.columns})
    if "Adj Close" not in df.columns and "Close" in df.columns:
        df["Adj Close"] = df["Close"]
    cols = [c for c in CANON_ORDER if c in df.columns] + [c for c in df.columns if c not in CANON_ORDER]
    return df[cols]

def _finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    # Hacer índice datetime
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df = df.dropna(subset=["Date"]).set_index("Date")
    elif "Datetime" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce", utc=True)
        df = df.dropna(subset=["Datetime"]).set_index("Datetime")
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce", utc=True)
        df = df.loc[~df.index.isna()]
    # Índice UTC-naive
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    # Columnas planas y limpieza
    df = _flatten_columns(df)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    key_cols = [c for c in ["Open","High","Low","Close"] if c in df.columns]
    if key_cols:
        df = df.dropna(subset=key_cols, how="all")
    return df

def _resolve_base_dir(raw_dir: Path, freq: str) -> Path:
    raw_dir = Path(raw_dir).resolve()
    if raw_dir.name == "raw":
        return raw_dir
    if raw_dir.name in ("1d","1h"):
        return raw_dir.parent
    ap = raw_dir.as_posix()
    if ap.endswith("/raw/1d") or ap.endswith("\\raw\\1d"):
        return raw_dir.parent
    if ap.endswith("/raw/1h") or ap.endswith("\\raw\\1h"):
        return raw_dir.parent
    return raw_dir

def _load_map(raw_dir: Path,
              tickers: Iterable[str],
              freq: str,
              aliases: Optional[dict],
              debug: bool=False) -> Dict[str, pd.DataFrame]:
    base_raw_dir = _resolve_base_dir(Path(raw_dir), freq)
    out: Dict[str, pd.DataFrame] = {}
    aliases = aliases or {}

    for t in tickers:
        tried: List[Path] = []

        # 1) Ticker original
        for p in _candidate_paths_for_ticker(base_raw_dir, t, freq):
            tried.append(p)
            if p.exists():
                try:
                    raw = _read_csv_generic(p)
                    df = _finalize_df(raw)
                    if not df.empty:
                        out[t] = df
                        break
                except Exception as e:
                    print(f"⚠️ Error leyendo {p}: {e}")
        if t in out:
            continue

        # 2) Alias efectivo
        t_eff = aliases.get(t, t)
        if t_eff != t:
            for p in _candidate_paths_for_ticker(base_raw_dir, t_eff, freq):
                tried.append(p)
                if p.exists():
                    try:
                        raw = _read_csv_generic(p)
                        df = _finalize_df(raw)
                        if not df.empty:
                            out[t] = df
                            break
                    except Exception as e:
                        print(f"⚠️ Error leyendo {p}: {e}")

        if t not in out:
            print(f"⚠️ {t}: sin datos {freq} encontrados en {base_raw_dir}")
            if debug:
                print("   Rutas probadas:")
                for p in tried:
                    print(f"   - {p}")

    return out

# ----------------------------- API pública -----------------------------

def load_daily_map(raw_1d_dir: str | Path,
                   tickers: Iterable[str],
                   aliases: Optional[dict]=None,
                   debug: bool=False) -> Dict[str, pd.DataFrame]:
    """Carga {ticker: DF diario} desde CSV. Acepta 'data/raw' o 'data/raw/1d'."""
    return _load_map(Path(raw_1d_dir), tickers, freq="1d", aliases=aliases, debug=debug)

def load_hourly_map(raw_1h_dir: str | Path,
                    tickers: Iterable[str],
                    aliases: Optional[dict]=None,
                    session_tag: Optional[str]=None,  # compat; ignorado
                    debug: bool=False) -> Dict[str, pd.DataFrame]:
    """Carga {ticker: DF 1h} desde CSV. Acepta 'data/raw' o 'data/raw/1h'."""
    return _load_map(Path(raw_1h_dir), tickers, freq="1h", aliases=aliases, debug=debug)
