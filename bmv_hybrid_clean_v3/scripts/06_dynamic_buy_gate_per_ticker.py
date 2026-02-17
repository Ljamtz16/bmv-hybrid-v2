# scripts/06_dynamic_buy_gate_per_ticker.py
from __future__ import annotations

import os, json
from pathlib import Path
import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta

from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals
from src.execution.hybrid_v2 import execute_hybrid_v2

# --------------------- Parámetros de la heurística ---------------------
GATE_WINDOW_MONTHS = 6   # ventana previa a evaluation.start
MIN_TRADES         = 6   # mínimo de trades BUY en la ventana
MIN_WINRATE        = 0.52  # ≥ 52% win rate
MIN_EXPECT         = 0.8   # ≥ 0.8 pnl medio por trade  (ajusta a tu escala)
# También puedes añadir una condición por PnL total si quieres:
MIN_PNL_SUM        = None  # por ejemplo 10.0; si None se ignora
# ----------------------------------------------------------------------

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

def pick_dates_between(idx: pd.DatetimeIndex, start_s: str, end_s: str) -> list[pd.Timestamp]:
    start = pd.Timestamp(start_s)
    end   = pd.Timestamp(end_s)
    return [d for d in idx if (start <= d < end)]

def first_available_ticker(d1_map: dict, tickers: list[str]) -> str | None:
    for t in tickers:
        if t in d1_map and d1_map[t] is not None and not d1_map[t].empty:
            return t
    return None

def run_backtest(sig_df: pd.DataFrame,
                 h1_map: dict[str, pd.DataFrame],
                 d1_map: dict[str, pd.DataFrame],
                 exec_cfg: dict) -> pd.DataFrame:
    rows = []
    if sig_df is None or sig_df.empty:
        return pd.DataFrame(rows)
    for _, s in sig_df.iterrows():
        t    = s["ticker"]
        D    = pd.to_datetime(s["date"]).date()
        side = str(s["side"])
        prob = float(s.get("prob", 0.0))
        if t not in h1_map or t not in d1_map or h1_map[t].empty or d1_map[t].empty:
            continue
        res = execute_hybrid_v2(
            h1_map, d1_map, t, D, side, prob,
            tp_mult=exec_cfg["tp_atr_mult"],
            sl_mult=exec_cfg["sl_atr_mult"],
            commission=exec_cfg["commission_pct"],
            slippage=exec_cfg["slippage_pct"],
            max_holding_days=exec_cfg["max_holding_days"],
            trail_atr_mult=exec_cfg.get("trail_atr_mult", 0.0),
            trail_activation_atr=exec_cfg.get("trail_activation_atr", 0.5),
            break_even_atr=exec_cfg.get("break_even_atr", 1.0),
        )
        rows.append(res)
    return pd.DataFrame(rows)

if __name__ == "__main__":
    cfg = load_cfg("config/base.yaml")

    # Sesión/tag
    sH, eH = cfg.session.split("-")
    tag = f"{sH.replace(':','')}_{eH.replace(':','')}"

    # Data
    aliases = getattr(cfg, "aliases", None)
    d1_map  = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map  = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # Modelos
    rf = svm = None
    try:
        import joblib
        if os.path.exists(cfg.models["rf_path"]): rf  = joblib.load(cfg.models["rf_path"])
        if os.path.exists(cfg.models["svm_path"]): svm = joblib.load(cfg.models["svm_path"])
    except Exception as e:
        print("⚠️ No RF/SVM:", e)
    lstm = LSTMSim()

    # τ por ticker si existe; si no, usa global
    tau_global_buy  = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))
    tau_by_ticker: dict = {}
    thr_path = "models/thresholds_by_ticker.json"
    if os.path.exists(thr_path):
        with open(thr_path, "r", encoding="utf-8") as f:
            tau_by_ticker = json.load(f)

    def tau_for(ticker: str, default_buy: float, default_sell: float) -> tuple[float, float]:
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", default_buy)), float(t.get("SELL", default_sell))

    # Ventana previa
    eval_start = pd.Timestamp(cfg.evaluation["start"])
    prev_start = (eval_start - relativedelta(months=GATE_WINDOW_MONTHS)).strftime("%Y-%m-%d")
    prev_end   = eval_start.strftime("%Y-%m-%d")

    # Fechas válidas a partir de un ancla
    anchor = first_available_ticker(d1_map, cfg.tickers)
    if anchor is None:
        raise RuntimeError("No hay datos diarios para ningún ticker.")
    idx = d1_map[anchor].index
    dates_prev = pick_dates_between(idx, prev_start, prev_end)
    if not dates_prev:
        raise RuntimeError(f"No hay datos para la ventana previa: {prev_start} → {prev_end}")

    # Generar señales por ticker (usando τ por ticker si existe)
    weights = (0.5, 0.3, 0.2)
    sig_list = []
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        tbuy, tsell = tau_for(t, tau_global_buy, tau_global_sell)
        sig_t = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, tbuy, tsell, [t], dates_prev, weights)
        if sig_t is not None and not sig_t.empty:
            sig_list.append(sig_t)
    sig_prev = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

    # Backtest solo BUY en la ventana previa
    exec_cfg = dict(
        tp_atr_mult=cfg.exec.tp_atr_mult,
        sl_atr_mult=cfg.exec.sl_atr_mult,
        commission_pct=cfg.exec.commission_pct,
        slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
        trail_atr_mult=cfg.exec.trail_atr_mult,
        trail_activation_atr=cfg.exec.trail_activation_atr,
        break_even_atr=cfg.exec.break_even_atr,
    )
    sig_prev_buy = sig_prev[sig_prev["side"] == "BUY"].copy()
    trades_prev  = run_backtest(sig_prev_buy, h1_map, d1_map, exec_cfg)

    # Agregación por ticker
    if trades_prev.empty:
        print("⚠️ No hubo trades BUY en la ventana previa; se habilitará BUY para todos por defecto.")
        gate_map = {t: True for t in cfg.tickers}
        detail = pd.DataFrame({"ticker": cfg.tickers, "trades": 0, "winrate": np.nan, "expectancy": np.nan, "pnl_sum": 0.0, "gate": True})
    else:
        trades_prev["pnl"] = trades_prev["pnl"].astype(float)
        agg = trades_prev.groupby("ticker").agg(
            trades=("pnl","count"),
            pnl_sum=("pnl","sum"),
            winrate=("pnl", lambda x: (x > 0).mean()),
            expectancy=("pnl", "mean"),
        ).reset_index()

        # Rellenar tickers sin trades
        missing = [t for t in cfg.tickers if t not in set(agg["ticker"])]
        if missing:
            extra = pd.DataFrame({"ticker": missing, "trades": 0, "pnl_sum": 0.0, "winrate": np.nan, "expectancy": np.nan})
            agg = pd.concat([agg, extra], ignore_index=True)

        def decide(row):
            tr = int(row["trades"])
            wr = float(row["winrate"]) if pd.notna(row["winrate"]) else 0.0
            ex = float(row["expectancy"]) if pd.notna(row["expectancy"]) else 0.0
            pn = float(row["pnl_sum"])
            cond_trades = tr >= MIN_TRADES
            cond_wr_ex  = (wr >= MIN_WINRATE) and (ex >= MIN_EXPECT)
            cond_pnl    = (MIN_PNL_SUM is not None) and (pn >= MIN_PNL_SUM)
            return bool(cond_trades and (cond_wr_ex or cond_pnl))

        agg["gate"] = agg.apply(decide, axis=1)
        gate_map = {r["ticker"]: bool(r["gate"]) for _, r in agg.iterrows()}
        detail = agg[["ticker","trades","winrate","expectancy","pnl_sum","gate"]].copy()

    # Salidas
    reports_dir = Path(cfg.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(reports_dir / "buy_gate_per_ticker.csv", index=False)

    models_dir = Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)
    with open(models_dir / "buy_gate.json", "w", encoding="utf-8") as f:
        json.dump(gate_map, f, indent=2)

    print(f"✅ Reporte por ticker guardado en {reports_dir/'buy_gate_per_ticker.csv'}")
    print(f"✅ Mapa compacto guardado en {models_dir/'buy_gate.json'}")
