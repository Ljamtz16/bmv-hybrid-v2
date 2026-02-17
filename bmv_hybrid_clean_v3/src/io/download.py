# src/io/download.py
from __future__ import annotations
import warnings
from pathlib import Path
import pandas as pd
import yfinance as yf
import yaml  # pip install pyyaml

# Silenciar FutureWarnings de yfinance
warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")

# Zona horaria de referencia (mercado MX) y normalización a UTC-naive
TZ_MX = "America/Mexico_City"

def to_utc_naive(ts) -> pd.Timestamp:
    t = pd.to_datetime(ts)
    if t.tzinfo is None:
        t = t.tz_localize(TZ_MX)
    return t.tz_convert("UTC").tz_localize(None)

def index_to_utc_naive(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        else:
            df = df.copy()
            df.index = df.index.tz_localize(TZ_MX).tz_convert("UTC").tz_localize(None)
    return df

# --------- NUEVO: normalización de columnas para evitar multi-header ---------
CANON_ORDER = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte columnas MultiIndex (p.ej. ('Close','ALSEA.MX')) a una sola capa."""
    if isinstance(df.columns, pd.MultiIndex):
        # Si el primer nivel son campos (Open/Close/...) úsalo; si no, intenta el segundo
        lvl0 = [c[0] for c in df.columns]
        if set(lvl0) & {"Open","High","Low","Close","Adj Close","Volume"}:
            df.columns = lvl0
        else:
            df.columns = [c[1] for c in df.columns]
    # Normaliza variantes de nombres comunes
    rename_map = {
        "open": "Open", "high": "High", "low": "Low", "close": "Close",
        "adj close": "Adj Close", "adj_close": "Adj Close", "adjclose": "Adj Close",
        "volume": "Volume",
    }
    df = df.rename(columns={c: rename_map.get(str(c).lower(), c) for c in df.columns})
    # Si falta Adj Close, crea copia de Close (mejor que nada)
    if "Adj Close" not in df.columns and "Close" in df.columns:
        df["Adj Close"] = df["Close"]
    # Reordena columnas dejando cualquier extra al final
    cols = [c for c in CANON_ORDER if c in df.columns] + [c for c in df.columns if c not in CANON_ORDER]
    df = df[cols]
    return df

def _finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica normalizaciones finales: índice UTC-naive, sin duplicados, columnas planas."""
    if df is None or df.empty:
        return df
    df = index_to_utc_naive(df)
    df = _flatten_columns(df)
    # Quita duplicados por índice y ordena
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df

def safe_download_start_end(ticker: str, start_utc_naive: pd.Timestamp, end_utc_naive: pd.Timestamp, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(
            ticker,
            start=start_utc_naive,
            end=end_utc_naive,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
            prepost=False,
        )
        return _finalize_df(df)
    except Exception as e:
        print(f"⚠️ {ticker} ({interval}) error start/end: {e}")
        return pd.DataFrame()

def safe_download_with_period(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
            prepost=False,
        )
        return _finalize_df(df)
    except Exception as e:
        print(f"❌ {ticker} period={period} ({interval}) falló: {e}")
        return pd.DataFrame()

def load_yaml_config(config_rel_path: str = "config/paper.yaml") -> dict:
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[2]
    cfg_path = (repo_root / config_rel_path).resolve()
    if not cfg_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}

def apply_alias_if_any(ticker: str, aliases: dict) -> str:
    if not aliases:
        return ticker
    return aliases.get(ticker, ticker)

def main():
    # 1) Config
    cfg = load_yaml_config("config/paper.yaml")
    tickers = list(cfg.get("tickers", []))
    if not tickers:
        raise ValueError("La lista 'tickers' en config/base.yaml está vacía o no existe.")

    aliases = cfg.get("aliases", {}) or {}
    disabled = set(cfg.get("disabled", []) or [])

    start_s = cfg.get("start", "2019-01-01")
    end_s   = cfg.get("end", pd.Timestamp.utcnow().strftime("%Y-%m-%d"))
    data_dir = cfg.get("data_dir", "data")

    d1_start = to_utc_naive(start_s)
    end_ts   = to_utc_naive(end_s)

    # Intradía estable por period
    INTRADAY_PERIOD = "729d"
    INTRADAY_INTERVAL = "1h"

    raw_dir = Path(data_dir) / "raw"
    raw_1d = raw_dir / "1d"
    raw_1h = raw_dir / "1h"
    raw_1d.mkdir(parents=True, exist_ok=True)
    raw_1h.mkdir(parents=True, exist_ok=True)

    if disabled:
        tickers = [t for t in tickers if t not in disabled]

    print(f"🧭 Config → tickers={len(tickers)}, start={start_s}, end={end_s}, data_dir={data_dir}")
    if aliases:
        print(f"🔁 Aliases activos: {aliases}")

    for t in tickers:
        t_eff = apply_alias_if_any(t, aliases)
        if t_eff != t:
            print(f"↪️  Alias: {t} → {t_eff}")

        print(f"↓ Descargando {t_eff}…")

        # Diario (1d) con start/end; si vacío, fallback con period largo
        d1 = safe_download_start_end(t_eff, d1_start, end_ts, interval="1d")
        if d1.empty:
            d1 = safe_download_with_period(t_eff, period="10y", interval="1d")
        if d1.empty:
            print(f"⚠️ {t_eff}: sin datos 1d (¿delisted?).")

        # Intradía (1h) por period (evita multiheaders/rangos inválidos)
        h1 = safe_download_with_period(t_eff, period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)
        if h1.empty:
            print(f"⚠️ {t_eff}: sin datos 1h (posible restricción / delisted / tz faltante).")

        # Guardar CSV con índice como columna "Date" (una sola fila de encabezados)
        if not d1.empty:
            d1.to_csv(raw_1d / f"{t_eff}_1d.csv", index_label="Date")
        if not h1.empty:
            h1.to_csv(raw_1h / f"{t_eff}_1h.csv", index_label="Date")

    print(f"✅ Datos descargados en {raw_dir}/")

if __name__ == "__main__":
    main()
