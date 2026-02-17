# scripts/09_make_month_forecast.py
from __future__ import annotations

# --- bootstrap para que 'src' se pueda importar ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# --------------------------------------------------

import os, json, argparse
import pandas as pd
import numpy as np

from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals

# ===== Utils =====

def first_available_ticker(d1_map: dict, tickers: list[str]) -> str | None:
    for t in tickers:
        if t in d1_map and d1_map[t] is not None and not d1_map[t].empty:
            return t
    return None

def ensure_atr_aliases_inplace(d1_map: dict[str, pd.DataFrame]) -> None:
    for t, df in d1_map.items():
        if df is None or df.empty:
            continue
        df2 = ensure_atr_14(df)
        if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
            df2["ATR_14"] = df2["ATR14"]
        if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
            df2["ATR14"] = df2["ATR_14"]
        d1_map[t] = df2

def month_span(ym: str) -> tuple[str, str]:
    """'YYYY-MM' -> (primer día del mes, primer día del mes siguiente) en YYYY-MM-DD."""
    y, m = map(int, ym.split("-"))
    start = pd.Timestamp(year=y, month=m, day=1)
    end = start + pd.offsets.MonthBegin(1)  # 1er día del mes siguiente (excluyente)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def pick_eval_dates(d1_map: dict[str, pd.DataFrame], tickers: list[str], start_s: str, end_s: str):
    anchor = first_available_ticker(d1_map, tickers)
    if anchor is None:
        raise RuntimeError("No hay datos diarios en d1_map para ningún ticker.")
    idx = d1_map[anchor].index
    start = pd.Timestamp(start_s)
    end = pd.Timestamp(end_s)
    return [d for d in idx if (start <= d < end)]

def load_buy_gate(path: Path) -> dict[str, bool]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            g = json.load(f)
        return {k: bool(v) for k, v in g.items()}
    return {}

def apply_buy_gate(sig: pd.DataFrame, gate: dict[str, bool]) -> pd.DataFrame:
    if sig is None or sig.empty or not gate:
        return sig
    allow_buy = sig["ticker"].map(lambda x: gate.get(x, True))
    mask_keep = (sig["side"] != "BUY") | allow_buy
    return sig.loc[mask_keep].reset_index(drop=True)

def build_forecast_features(
    d1_map: dict[str, pd.DataFrame],
    tickers: list[str],
    dates_eval: list[pd.Timestamp],
    sig_df: pd.DataFrame | None = None,
    prob_col_out: str = "prob_win",
) -> pd.DataFrame:
    """
    Construye un DataFrame de features por (ticker, date) limitado a 'dates_eval'
    y exporta columnas clave:
      - ticker, date
      - entry_price  (close del día)
      - ret_20d_vol  (std rolling 20d de pct_change)
    Une opcionalmente la probabilidad como 'prob_win' si está en sig_df.
    """
    feat_list = []

    # 1) Precalcular volatilidad 20d en TODO el histórico por ticker
    vol_map: dict[str, pd.Series] = {}
    for t in tickers:
        df_full = d1_map.get(t)
        if df_full is None or df_full.empty:
            continue
        if "close" not in df_full.columns:
            continue
        s_close = pd.to_numeric(df_full["close"], errors="coerce")
        ret = s_close.pct_change()
        vol = ret.rolling(20, min_periods=10).std()
        vol_map[t] = vol

    # 2) Recortar a las fechas del mes objetivo y construir features
    for t in tickers:
        df = d1_map.get(t)
        if df is None or df.empty:
            continue

        dfi = df.loc[df.index.isin(dates_eval)].copy()
        if dfi.empty:
            continue

        dfi = dfi.reset_index().rename(columns={"index": "date"})
        if "date" not in dfi.columns:
            possible_date_cols = [c for c in dfi.columns if str(c).lower() in ("date","fecha")]
            if possible_date_cols:
                dfi = dfi.rename(columns={possible_date_cols[0]: "date"})
            else:
                raise RuntimeError("No se encontró columna de fecha tras reset_index().")

        dfi["ticker"] = t

        # entry_price = close del día
        if "close" in dfi.columns:
            dfi["entry_price"] = pd.to_numeric(dfi["close"], errors="coerce")
        elif "Close" in dfi.columns:
            dfi["entry_price"] = pd.to_numeric(dfi["Close"], errors="coerce")
        else:
            dfi["entry_price"] = np.nan

        # ret_20d_vol desde el precálculo (unimos por fecha)
        vol_ser = vol_map.get(t)
        if vol_ser is not None and not vol_ser.empty:
            dfi = dfi.merge(
                vol_ser.rename("ret_20d_vol").reset_index().rename(columns={"index": "date"}),
                on="date", how="left"
            )
        else:
            dfi["ret_20d_vol"] = np.nan

        cols_first = ["ticker", "date", "entry_price", "ret_20d_vol"]
        other_cols = [c for c in dfi.columns if c not in cols_first]
        dfi = dfi[cols_first + other_cols]
        feat_list.append(dfi)

    if not feat_list:
        return pd.DataFrame(columns=["ticker","date","entry_price","ret_20d_vol"])

    df_features = pd.concat(feat_list, ignore_index=True)

    # 3) Merge opcional con probabilidad (prob -> prob_win)
    if sig_df is not None and not sig_df.empty:
        def _to_ts(s):
            return pd.to_datetime(s).dt.tz_localize(None)
        df_features["date"] = _to_ts(df_features["date"])
        sig_tmp = sig_df.copy()
        if "prob" in sig_tmp.columns and prob_col_out not in sig_tmp.columns:
            sig_tmp = sig_tmp.rename(columns={"prob": prob_col_out})
        sig_tmp["date"] = _to_ts(sig_tmp["date"])
        cols_join = ["ticker","date"] + [c for c in sig_tmp.columns if c not in ("ticker","date")]
        sig_tmp = sig_tmp[cols_join]
        df_features = df_features.merge(sig_tmp, on=["ticker","date"], how="left")

    df_features = df_features.sort_values(["ticker","date"]).reset_index(drop=True)
    return df_features

def add_forecast_features(df):
    # entry_price y ret_20d_vol de origen si existen
    if "entry_price" in df.columns:
        df["entry_price"] = df["entry_price"]
    if "ret_20d_vol" in df.columns:
        df["ret_20d_vol"] = df["ret_20d_vol"]
    return df

# ===== Main =====

def parse_args():
    p = argparse.ArgumentParser(description="Generar pronóstico de señales para un mes (YYYY-MM).")
    p.add_argument("--month", required=True, type=str, help="Mes objetivo, p.ej. 2025-03")
    p.add_argument("--gate", default="auto", choices=["auto","true","false"],
                   help="Cómo aplicar buy gate al pronóstico (default auto)")
    p.add_argument("--min-prob", type=float, default=0.0, help="Umbral mínimo de probabilidad para filtrar señales")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    cfg_path = os.environ.get("CFG", "config/base.yaml")
    cfg = load_cfg(cfg_path)

    ym = args.month
    eval_start, eval_end = month_span(ym)

    # Sesión/tag
    sH, eH = cfg.session.split("-")
    tag_session = f"{sH.replace(':','')}_{eH.replace(':','')}"

    # Datos
    aliases = getattr(cfg, "aliases", None)
    d1_root = os.path.join(cfg.data_dir, "raw", "1d")
    h1_root = os.path.join(cfg.data_dir, "raw", "1h")
    d1_map = load_daily_map(d1_root, cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(h1_root, cfg.tickers, aliases=aliases, session_tag=tag_session, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # Modelos
    rf = svm = None
    try:
        import joblib
        if os.path.exists(cfg.models["rf_path"]):
            rf = joblib.load(cfg.models["rf_path"])
        if os.path.exists(cfg.models["svm_path"]):
            svm = joblib.load(cfg.models["svm_path"])
    except Exception as e:
        print("⚠️ No RF/SVM:", e)
    lstm = LSTMSim()

    # τ
    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))
    tau_by_ticker: dict = {}
    thr_path = "models/thresholds_by_ticker.json"
    if os.path.exists(thr_path):
        with open(thr_path, "r", encoding="utf-8") as f:
            tau_by_ticker = json.load(f)

    def tau_for(ticker: str) -> tuple[float, float]:
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", tau_global_buy)), float(t.get("SELL", tau_global_sell))

    # Fechas del mes
    dates_eval = pick_eval_dates(d1_map, cfg.tickers, eval_start, eval_end)
    if not dates_eval:
        print(f"⚠️ No hay barras diarias entre {eval_start} y {eval_end}. "
              f"Asegura que tu data 1D esté actualizada antes de pronosticar {ym}.")
        raise SystemExit(1)

    # Generar señales
    weights = (0.5, 0.3, 0.2)
    sig_list = []
    min_prob = getattr(args, "min-prob".replace("-", "_"), 0.0)  # asegurar acceso seguro
    min_prob = args.min_prob if hasattr(args, "min_prob") else 0.0

    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        tb, ts = tau_for(t)
        sig_t = generate_daily_signals(
            {t: d1_map[t]}, rf, svm, lstm, tb, ts, [t], dates_eval, weights,
            min_prob=min_prob
        )
        if sig_t is not None and not sig_t.empty:
            sig_list.append(sig_t)

    sig = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

    # Buy gate
    buy_gate_path = Path("models/buy_gate.json")
    buy_gate = load_buy_gate(buy_gate_path)

    mode = args.gate
    if mode == "true":
        sig_used = apply_buy_gate(sig, buy_gate)
        gate_tag = "with_gate"
    elif mode == "false" or not buy_gate:
        sig_used = sig.copy()
        gate_tag = "no_gate"
    else:
        # auto: calculamos ambas variantes
        sig_used = sig.copy()
        gate_tag = "auto"

    # Guardar pronóstico
    out_dir = Path(getattr(cfg, "reports_dir", "reports")) / "forecast" / ym
    out_dir.mkdir(parents=True, exist_ok=True)

    base_csv = out_dir / f"forecast_{ym}_base.csv"
    sig.to_csv(base_csv, index=False, encoding="utf-8")

    if gate_tag == "with_gate":
        out_csv = out_dir / f"forecast_{ym}_with_gate.csv"
        sig_used.to_csv(out_csv, index=False, encoding="utf-8")
    elif gate_tag == "no_gate":
        out_csv = out_dir / f"forecast_{ym}_no_gate.csv"
        sig_used.to_csv(out_csv, index=False, encoding="utf-8")
    else:
        out_csv_ng = out_dir / f"forecast_{ym}_no_gate.csv"
        out_csv_wg = out_dir / f"forecast_{ym}_with_gate.csv"
        sig.to_csv(out_csv_ng, index=False, encoding="utf-8")
        apply_buy_gate(sig, buy_gate).to_csv(out_csv_wg, index=False, encoding="utf-8")
        out_csv = out_csv_wg  # evitar NameError en el print final

    # ========= Exportar features del forecast (con entry_price y ret_20d_vol) =========
    try:
        df_features = build_forecast_features(
            d1_map=d1_map,
            tickers=cfg.tickers,
            dates_eval=dates_eval,
            sig_df=sig,             # incorpora 'prob' como 'prob_win' si existe
            prob_col_out="prob_win"
        )
        df_features = add_forecast_features(df_features)
        feat_out = Path("reports/forecast/latest_forecast_features.csv")
        feat_out.parent.mkdir(parents=True, exist_ok=True)
        df_features.to_csv(feat_out, index=False, encoding="utf-8")
        print(f"📂 Features exportadas a {feat_out} (filas={len(df_features):,})")
    except Exception as e:
        print(f"⚠️ No se pudieron exportar features de forecast: {e}")

    # Meta
    meta = {
        "month": ym,
        "eval_start": eval_start,
        "eval_end": eval_end,
        "cfg_path": cfg_path,
        "gate_mode": mode,
        "buy_gate_present": bool(buy_gate),
        "weights": list(weights)
    }
    with (out_dir / "meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"✅ Pronóstico generado en {out_dir}")
    print(f"   Base: {base_csv} | Usado: {out_csv} (modo={gate_tag})")
    if gate_tag == "auto":
        print(f"   No gate: {out_csv_ng} | Con gate: {out_csv_wg}")
