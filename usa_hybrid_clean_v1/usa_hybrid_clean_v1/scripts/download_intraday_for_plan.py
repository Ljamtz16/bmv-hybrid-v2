"""download_intraday_for_plan.py

Descarga resiliente intradía para los tickers del trade plan y genera:
 - Buffer snapshot (CSV simple) para monitores existentes.
 - Parquet enriquecido con timestamps duales (UTC / America/New_York).
 - Métricas de latencia y cobertura (outputs/intraday_metrics.csv).
 - Lista de fallidos (outputs/intraday_missing.csv).

Mejoras clave:
 - Retry con exponential backoff.
 - Detección de gap >3% respecto al último close diario (ignora primera barra).
 - Concurrencia (ThreadPoolExecutor) hasta N workers.
 - Smart cache: si buffer reciente (<30s) se omite descarga.
"""
import argparse
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

try:  # yfinance opcional, validamos al usar
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

BUFFER_DIR = Path("data/intraday5/buffer")
ENRICH_DIR = Path("data/intraday")  # parquet enriquecido
HISTORY_DIR = Path("data/intraday15/history")
OUTPUTS_DIR = Path("outputs")

DAILY_REF = Path("data/daily/ohlcv_us_daily.csv")  # archivo diario para gap detection (close T-1)


def _load_last_daily_close_map():
    if not DAILY_REF.exists():
        logging.warning("[daily_ref] No existe archivo diario para gap detection; se omite.")
        return {}
    try:
        df = pd.read_csv(DAILY_REF, parse_dates=[c for c in ["timestamp", "date"] if c in DAILY_REF.name])
    except Exception as e:
        logging.warning(f"[daily_ref] Error leyendo {DAILY_REF}: {e}")
        return {}
    # Inferir columnas
    col_ticker = 'ticker' if 'ticker' in df.columns else None
    col_close = 'close' if 'close' in df.columns else ('Close' if 'Close' in df.columns else None)
    if not col_ticker or not col_close:
        logging.warning("[daily_ref] Formato inesperado (sin ticker/close)")
        return {}
    # ordenar y tomar último por ticker
    last_map = {}
    for tk, g in df.groupby(col_ticker):
        try:
            last_close = float(g.sort_values(by=g.columns.tolist()).iloc[-1][col_close])
            last_map[str(tk).upper()] = last_close
        except Exception:
            continue
    return last_map


def smart_cache_recent(ticker: str, interval: str) -> bool:
    """Devuelve True si existe parquet reciente (<30s) y podemos saltar descarga."""
    fp = ENRICH_DIR / f"{ticker}_{interval}.parquet"
    if not fp.exists():
        return False
    try:
        mtime = fp.stat().st_mtime
        age = time.time() - mtime
        return age < 30.0
    except Exception:
        return False


def download_one(ticker: str, interval: str, days: int, last_daily_close: float | None, max_retries: int = 3):
    start_perf = time.perf_counter()
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    delay = 1.0
    last_exc = None
    df = None
    for attempt in range(1, max_retries + 1):
        try:
            df = yf.download(
                ticker,
                start=start_dt,
                end=end_dt,
                interval=interval,
                progress=False,
                auto_adjust=False,
                actions=False,
                repair=True,
                prepost=False
            )
            if df is not None and not df.empty:
                break
            raise ValueError("Empty intraday frame")
        except Exception as e:  # pragma: no cover (network dependent)
            last_exc = e
            logging.warning(f"[{ticker}] retry {attempt}/{max_retries}: {e}")
            time.sleep(delay)
            delay *= 2
    else:
        return None, {"ticker": ticker, "ok": False, "latency_s": round(time.perf_counter() - start_perf, 3)}

    # Normalizar TZ índice
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    # Dual timestamps
    df["timestamp_utc"] = df.index.tz_convert("UTC")
    try:
        df["timestamp_ny"] = df.index.tz_convert("America/New_York")
    except Exception:  # fallback si tz no disponible
        df["timestamp_ny"] = df["timestamp_utc"]

    # Gap detection (primera barra vs close T-1)
    if last_daily_close and len(df) > 0:
        try:
            first_open = float(df.iloc[0]["Open"])
            gap = abs(first_open - last_daily_close) / last_daily_close
            if gap > 0.03:
                logging.info(f"[{ticker}] gap {gap:.1%} -> ignorando primera barra")
                df = df.iloc[1:].copy()
        except Exception:
            pass

    latency = round(time.perf_counter() - start_perf, 3)
    return df, {"ticker": ticker, "ok": True, "latency_s": latency}


def save_buffer_snapshot(ticker: str, df: pd.DataFrame):
    """Guarda último close simple para compatibilidad con monitores previos."""
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    if df.empty:
        return
    last_row = df.iloc[-1]
    if "Close" in df.columns:
        val = last_row["Close"]
        # Evitar FutureWarning: si es Series de un elemento, usar iloc[0]
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        close_val = float(val)
    else:
        numeric_cols = last_row.select_dtypes("number")
        close_val = float(numeric_cols.iloc[0]) if len(numeric_cols) > 0 else 0.0
    snapshot = pd.DataFrame({"timestamp": [df.index[-1].isoformat()], "close": [close_val]})
    (BUFFER_DIR / f"{ticker}_last.csv").write_text(snapshot.to_csv(index=False))
    logging.info(f"[OK] {ticker} buffer close={close_val:.2f}")


def save_parquet(ticker: str, interval: str, df: pd.DataFrame):
    ENRICH_DIR.mkdir(parents=True, exist_ok=True)
    out = ENRICH_DIR / f"{ticker}_{interval}.parquet"
    df.to_parquet(out, index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="val/trade_plan.csv", help="Ruta al trade plan CSV")
    ap.add_argument("--interval", default="5m", help="Intervalo intradía (5m, 15m, 30m, 60m)")
    ap.add_argument("--days", type=int, default=1, help="Días de historial a descargar")
    # yfinance puede comportarse de forma no thread-safe; por defecto 1 worker
    ap.add_argument("--max-workers", type=int, default=1, help="Máximo hilos descarga (default=1 por estabilidad)")
    ap.add_argument("--skip-recent", action="store_true", help="Activar smart cache (omitir si parquet <30s)")
    ap.add_argument("--save-history", action="store_true", help="Guardar CSV histórico completo")
    ap.add_argument("--dry-run", action="store_true", help="No descargar, solo mostrar acciones")
    args = ap.parse_args()

    OUTPUTS_DIR.mkdir(exist_ok=True)

    if not os.path.exists(args.plan):
        logging.error(f"No se encuentra trade plan: {args.plan}")
        return
    plan = pd.read_csv(args.plan)
    if "ticker" not in plan.columns:
        logging.error("Trade plan sin columna 'ticker'")
        return
    tickers = sorted(set(plan["ticker"].astype(str).str.upper()))
    logging.info(f"[intraday] {len(tickers)} tickers interval={args.interval} days={args.days}")

    if args.dry_run:
        for t in tickers:
            logging.info(f"[DRY] {t}")
        logging.info("[DRY] Done")
        return
    if yf is None:
        logging.error("yfinance no instalado. Instala con: python -m pip install yfinance")
        return

    last_close_map = _load_last_daily_close_map()
    metrics = []
    missing = []

    def _task(tk: str):
        if args.skip_recent and smart_cache_recent(tk, args.interval):
            return None, {"ticker": tk, "ok": True, "latency_s": 0.0, "skipped": True}
        return download_one(tk, args.interval, args.days, last_close_map.get(tk))

    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(tickers) or 1)) as ex:
        futs = {ex.submit(_task, tk): tk for tk in tickers}
        for fut in as_completed(futs):
            tk = futs[fut]
            try:
                df, meta = fut.result()
            except Exception as e:  # pragma: no cover
                logging.error(f"[{tk}] excepción inesperada: {e}")
                df, meta = None, {"ticker": tk, "ok": False, "latency_s": None}
            metrics.append(meta)
            if not meta.get("ok"):
                missing.append(tk)
                continue
            if meta.get("skipped"):
                logging.info(f"[{tk}] saltado por smart cache")
                continue
            if df is None or df.empty:
                missing.append(tk)
                continue
            save_parquet(tk, args.interval, df)
            save_buffer_snapshot(tk, df)
            if args.save_history:
                HISTORY_DIR.mkdir(parents=True, exist_ok=True)
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                df.to_csv(HISTORY_DIR / f"{tk}_{date_str}.csv")

    # Cobertura & métricas
    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(OUTPUTS_DIR / "intraday_metrics.csv", index=False)
    if missing:
        pd.DataFrame({"ticker": missing}).to_csv(OUTPUTS_DIR / "intraday_missing.csv", index=False)
    ok_count = metrics_df[metrics_df["ok"] == True].shape[0]
    logging.info(f"[intraday] Descarga completada OK={ok_count}/{len(tickers)} Missing={len(missing)}")


if __name__ == "__main__":
    main()
