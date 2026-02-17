# scripts/05_2_optimizer.py
from __future__ import annotations
import os, json
from pathlib import Path
import pandas as pd
import numpy as np

from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals
from src.execution.hybrid_v2 import execute_hybrid_v2

def ensure_atr_aliases_inplace(d1_map):
    for t, df in d1_map.items():
        if df is None or df.empty: 
            continue
        df2 = ensure_atr_14(df)
        if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
            df2["ATR_14"] = df2["ATR14"]
        if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
            df2["ATR14"] = df2["ATR_14"]
        d1_map[t] = df2

def first_available_ticker(d1_map, tickers):
    for t in tickers:
        if t in d1_map and d1_map[t] is not None and not d1_map[t].empty:
            return t
    return None

def pick_eval_dates(d1_map, tickers, start_s, end_s):
    anchor = first_available_ticker(d1_map, tickers)
    if anchor is None:
        raise RuntimeError("No hay datos diarios en d1_map.")
    idx = d1_map[anchor].index
    start, end = pd.Timestamp(start_s), pd.Timestamp(end_s)
    return [d for d in idx if (start <= d < end)]

def run_backtest(sig_df, h1_map, d1_map, exec_cfg):
    rows = []
    if sig_df is None or sig_df.empty:
        return pd.DataFrame(rows)
    for _, s in sig_df.iterrows():
        t = s["ticker"]; D = pd.to_datetime(s["date"]).date()
        side = str(s["side"]); prob = float(s.get("prob", 0.0))
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
    if trades_df is None or trades_df.empty:
        return {"Trades": 0, "WinRate_%": 0.0, "PnL_sum": 0.0, "MDD": 0.0, "Sharpe": 0.0, "Expectancy": 0.0}
    df = trades_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["equity"] = df["pnl"].cumsum()
    roll_max = df["equity"].cummax()
    drawdown = df["equity"] - roll_max
    mdd = float(-(drawdown.min() if not drawdown.empty else 0.0))
    ret = df["pnl"]
    sharpe = float(ret.mean() / (ret.std(ddof=1) + 1e-12) * np.sqrt(252)) if len(ret) > 1 else 0.0
    expectancy = float(ret.mean()) if not ret.empty else 0.0
    return {
        "Trades": int(df.shape[0]),
        "WinRate_%": float(round((df["pnl"] > 0).mean() * 100.0, 2)),
        "PnL_sum": float(round(df["pnl"].sum(), 2)),
        "MDD": float(round(mdd, 2)),
        "Sharpe": float(round(sharpe, 2)),
        "Expectancy": float(round(expectancy, 2)),
    }

if __name__ == "__main__":
    import pandas as pd

    cfg = load_cfg("config/base.yaml")
    reports_dir = Path(cfg.reports_dir if hasattr(cfg, "reports_dir") else "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # datos
    sH, eH = cfg.session.split("-"); tag = f"{sH.replace(':','')}_{eH.replace(':','')}"
    aliases = getattr(cfg, "aliases", None)
    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # modelos
    rf = svm = None
    try:
        import joblib
        if os.path.exists(cfg.models["rf_path"]): rf = joblib.load(cfg.models["rf_path"])
        if os.path.exists(cfg.models["svm_path"]): svm = joblib.load(cfg.models["svm_path"])
    except Exception as e:
        print("⚠️ No RF/SVM:", e)
    lstm = LSTMSim()

    # thresholds por ticker (si existen)
    tau_by_ticker = {}
    thr_path = "models/thresholds_by_ticker.json"
    if os.path.exists(thr_path):
        with open(thr_path, "r", encoding="utf-8") as f:
            tau_by_ticker = json.load(f)
    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))

    def tau_for(ticker, default_buy, default_sell):
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", default_buy)), float(t.get("SELL", default_sell))

    # fechas
    eval_start, eval_end = cfg.evaluation["start"], cfg.evaluation["end"]
    dates_eval = pick_eval_dates(d1_map, cfg.tickers, eval_start, eval_end)

    # espacio de búsqueda (ajústalo a gusto)
    tp_values = [1.4, 1.5, 1.6, 1.7, 1.8]
    sl_values = [0.7, 0.8, 0.9, 1.0]
    trails = [
        {"trail_atr_mult": 0.0, "trail_activation_atr": 0.5, "break_even_atr": 1.0, "name": "no_trail"},
        {"trail_atr_mult": 0.6, "trail_activation_atr": 0.6, "break_even_atr": 0.8, "name": "trail_mid"},
        {"trail_atr_mult": 0.8, "trail_activation_atr": 0.5, "break_even_atr": 0.7, "name": "trail_aggr"},
    ]

    base_exec = dict(
        commission_pct=cfg.exec.commission_pct,
        slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
    )

    weights = (0.5, 0.3, 0.2)
    summary = []

    for tp in tp_values:
        for sl in sl_values:
            for tr in trails:
                scen_name = f"tp{tp}_sl{sl}_{tr['name']}"
                # generar señales (τ por ticker)
                sig_list = []
                for tkr in cfg.tickers:
                    if tkr not in d1_map or d1_map[tkr].empty:
                        continue
                    t_buy, t_sell = tau_for(tkr, tau_global_buy, tau_global_sell)
                    sig_t = generate_daily_signals({tkr: d1_map[tkr]}, rf, svm, lstm, t_buy, t_sell, [tkr], dates_eval, weights)
                    if sig_t is not None and not sig_t.empty:
                        sig_list.append(sig_t)
                sig_df = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

                exec_cfg = dict(
                    tp_atr_mult=tp,
                    sl_atr_mult=sl,
                    trail_atr_mult=tr["trail_atr_mult"],
                    trail_activation_atr=tr["trail_activation_atr"],
                    break_even_atr=tr["break_even_atr"],
                    **base_exec
                )

                trades = run_backtest(sig_df, h1_map, d1_map, exec_cfg)
                trades.to_csv(reports_dir / f"opt_trades_{scen_name}.csv", index=False)
                met = kpis(trades); met["scenario"] = scen_name
                summary.append(met)
                print(f"{scen_name}: {met}")

    df = pd.DataFrame(summary).sort_values(["PnL_sum","Sharpe"], ascending=[False, False])
    df.to_csv(reports_dir / "optimizer_summary.csv", index=False)
    print("\n✅ Optimización finalizada. Revisa reports/optimizer_summary.csv")
