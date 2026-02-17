# scripts/_eval_core.py
from __future__ import annotations

import os, json
from pathlib import Path
import pandas as pd
import numpy as np

from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals
from src.execution.hybrid_v2 import execute_hybrid_v2

# ---------------------------- Helpers locales ----------------------------

def ensure_atr_aliases_inplace(d1_map: dict[str, pd.DataFrame]) -> None:
    """Garantiza columnas ATR14 y/o ATR_14 en los DFs diarios."""
    for t, df in d1_map.items():
        if df is None or df.empty:
            continue
        df2 = ensure_atr_14(df)
        if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
            df2["ATR_14"] = df2["ATR14"]
        if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
            df2["ATR14"] = df2["ATR_14"]
        d1_map[t] = df2

def first_available_ticker(d1_map: dict, tickers: list[str]) -> str | None:
    for t in tickers:
        if t in d1_map and d1_map[t] is not None and not d1_map[t].empty:
            return t
    return None

def pick_eval_dates(d1_map: dict[str, pd.DataFrame], tickers: list[str], start_s: str, end_s: str):
    """Devuelve lista de fechas (índice de D1) en [start, end)."""
    anchor = first_available_ticker(d1_map, tickers)
    if anchor is None:
        raise RuntimeError("No hay datos diarios en d1_map para ningún ticker.")
    idx = d1_map[anchor].index
    start = pd.Timestamp(start_s)
    end = pd.Timestamp(end_s)
    return [d for d in idx if (start <= d < end)]

def run_backtest(sig_df: pd.DataFrame,
                 h1_map: dict[str, pd.DataFrame],
                 d1_map: dict[str, pd.DataFrame],
                 exec_cfg: dict) -> pd.DataFrame:
    """
    Ejecuta cada señal con execute_hybrid_v2 y devuelve un DataFrame de trades.
    Requiere columnas: ['ticker','date','side','prob'] en sig_df.
    """
    rows = []
    if sig_df is None or sig_df.empty:
        return pd.DataFrame(rows)

    for _, s in sig_df.iterrows():
        t = s["ticker"]
        D = pd.to_datetime(s["date"]).date()
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

def kpis(trades_df: pd.DataFrame) -> dict:
    """KPIs básicos + Sharpe/MDD/Expectancy."""
    if trades_df is None or trades_df.empty:
        return {"Trades": 0, "WinRate_%": 0.0, "PnL_sum": 0.0, "MDD": 0.0, "Sharpe": 0.0, "Expectancy": 0.0}
    t = int(trades_df.shape[0])
    winrate = float((trades_df["pnl"] > 0).mean() * 100.0)
    pnl_sum = float(trades_df["pnl"].sum())
    eq = trades_df["pnl"].cumsum()
    roll_max = eq.cummax()
    dd = eq - roll_max
    mdd = float(-dd.min())
    ret = trades_df["pnl"]
    sharpe = float(ret.mean() / (ret.std(ddof=1) + 1e-12) * np.sqrt(252))
    expectancy = float(ret.mean())
    return {
        "Trades": t,
        "WinRate_%": round(winrate, 2),
        "PnL_sum": round(pnl_sum, 2),
        "MDD": round(mdd, 2),
        "Sharpe": round(sharpe, 2),
        "Expectancy": round(expectancy, 2),
    }

def load_buy_gate(path: Path) -> dict[str, bool]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            g = json.load(f)
        return {k: bool(v) for k, v in g.items()}
    return {}

def apply_buy_gate(sig: pd.DataFrame, gate: dict[str, bool]) -> pd.DataFrame:
    """Filtra señales BUY por ticker según gate {ticker: True/False}."""
    if sig is None or sig.empty or not gate:
        return sig
    allow_buy = sig["ticker"].map(lambda x: gate.get(x, True))
    mask_keep = (sig["side"] != "BUY") | allow_buy
    return sig.loc[mask_keep].reset_index(drop=True)

# ---------------------------- API pública: run_once_day ----------------------------

def run_once_day(cfg,
                 eval_start: str,
                 eval_end: str,
                 dump_dir: Path | None = None) -> dict:
    """
    Ejecuta evaluación en una ventana corta [eval_start, eval_end) usando la config dada.
    Respeta el modo de BUY gate definido en cfg.signals.apply_buy_gate: 'auto'|'true'|'false' (default 'auto').

    Devuelve un dict con KPIs:
      {Trades, WinRate_%, PnL_sum, MDD, Sharpe, Expectancy, buy_gate}
    y, si dump_dir se provee, guarda signals/trades usados.
    """
    # --- Datos ---
    sH, eH = cfg.session.split("-")
    tag_session = f"{sH.replace(':','')}_{eH.replace(':','')}"
    aliases = getattr(cfg, "aliases", None)

    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag_session, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # --- Modelos ---
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

    # --- τ (por ticker si hay archivo, si no global) ---
    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))

    tau_by_ticker: dict = {}
    thr_path = "models/thresholds_by_ticker.json"
    if os.path.exists(thr_path):
        with open(thr_path, "r", encoding="utf-8") as f:
            tau_by_ticker = json.load(f)

    def tau_for(ticker: str, default_buy: float, default_sell: float) -> tuple[float, float]:
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", default_buy)), float(t.get("SELL", default_sell))

    # --- Fechas / señales ---
    dates_eval = pick_eval_dates(d1_map, cfg.tickers, eval_start, eval_end)
    if not dates_eval:
        return {"error": f"Sin fechas entre {eval_start} y {eval_end}", "Trades": 0, "PnL_sum": 0.0}

    weights = (0.5, 0.3, 0.2)
    sig_list = []
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        t_buy, t_sell = tau_for(t, tau_global_buy, tau_global_sell)
        sig_t = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, t_buy, t_sell, [t], dates_eval, weights)
        if sig_t is not None and not sig_t.empty:
            sig_list.append(sig_t)
    sig = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

    # --- Exec config ---
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

    # --- BUY gate policy ---
    buy_gate_path = Path("models/buy_gate.json")
    buy_gate = load_buy_gate(buy_gate_path)
    signals_cfg = getattr(cfg, "signals", {}) or {}
    apply_mode = str(signals_cfg.get("apply_buy_gate", "auto")).lower()  # 'auto'|'true'|'false'

    def run_variant(sig_df, tag_suffix):
        trades = run_backtest(sig_df, h1_map, d1_map, exec_cfg)
        k = kpis(trades)
        if dump_dir:
            dump_dir.mkdir(parents=True, exist_ok=True)
            sig_df.to_csv(dump_dir / f"signals_{tag_suffix}.csv", index=False)
            trades.to_csv(dump_dir / f"trades_{tag_suffix}.csv", index=False)
        return trades, k

    if apply_mode == "false" or (apply_mode == "true" and not buy_gate):
        # sin gate (o forzado true pero no hay json → fallback sin gate)
        trades, kp = run_variant(sig, "no_gate")
        gate_tag = "gateOff" if apply_mode == "false" else "gateRequestedButMissing"
    elif apply_mode == "true":
        sig_yes = apply_buy_gate(sig, buy_gate)
        trades, kp = run_variant(sig_yes, "with_gate")
        gate_tag = "gateOn"
    else:
        # auto: comparar ambas variantes
        trades_no, k_no = run_variant(sig.copy(), "no_gate")
        sig_yes = apply_buy_gate(sig, buy_gate)
        trades_yes, k_yes = run_variant(sig_yes, "with_gate")

        pick_with = (k_yes["PnL_sum"] > k_no["PnL_sum"]) or (k_yes["PnL_sum"] == k_no["PnL_sum"] and k_yes["Sharpe"] > k_no["Sharpe"])
        trades, kp = (trades_yes, k_yes) if pick_with else (trades_no, k_no)
        gate_tag = "gateAutoYes" if pick_with else "gateAutoNo"

    # --- resultado ---
    kp["buy_gate"] = gate_tag
    kp["eval_start"] = eval_start
    kp["eval_end"] = eval_end
    return kp
