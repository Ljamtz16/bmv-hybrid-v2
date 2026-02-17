# scripts/05_3_trail_tune.py
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

def run_backtest(sig_df, h1_map, d1_map, exec_cfg):
    rows = []
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

def kpis(trades_df):
    if trades_df.empty:
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
    return {"Trades": int(df.shape[0]), "WinRate_%": round((df["pnl"]>0).mean()*100,2),
            "PnL_sum": round(float(df["pnl"].sum()),2), "MDD": round(mdd,2),
            "Sharpe": round(sharpe,2), "Expectancy": round(expectancy,2)}

if __name__ == "__main__":
    cfg = load_cfg("config/base.yaml")
    sH,eH = cfg.session.split("-"); tag = f"{sH.replace(':','')}_{eH.replace(':','')}"
    aliases = getattr(cfg, "aliases", None)

    d1_map = load_daily_map(os.path.join(cfg.data_dir,"raw","1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir,"raw","1h"), cfg.tickers, aliases=aliases, session_tag=tag, debug=False)
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

    # τ por ticker (si existe)
    tau_by_ticker = {}
    if os.path.exists("models/thresholds_by_ticker.json"):
        with open("models/thresholds_by_ticker.json","r",encoding="utf-8") as f:
            tau_by_ticker = json.load(f)
    tau_global_buy = float(getattr(cfg,"calibration",{}).get("tau_star",{}).get("BUY",0.5))
    tau_global_sell= float(getattr(cfg,"calibration",{}).get("tau_star",{}).get("SELL",0.5))
    def tau_for(ticker, default_buy, default_sell):
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", default_buy)), float(t.get("SELL", default_sell))

    # fechas
    eval_start, eval_end = cfg.evaluation["start"], cfg.evaluation["end"]
    anchor = next(t for t in cfg.tickers if t in d1_map and not d1_map[t].empty)
    idx = d1_map[anchor].index
    dates_eval = [d for d in idx if (pd.Timestamp(eval_start) <= d < pd.Timestamp(eval_end))]

    # señales (τ por ticker)
    weights = (0.5,0.3,0.2)
    sig_list = []
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty: continue
        t_buy, t_sell = tau_for(t, tau_global_buy, tau_global_sell)
        s = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, t_buy, t_sell, [t], dates_eval, weights)
        if s is not None and not s.empty: sig_list.append(s)
    sig = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

    # base exec fijando tp/sl en 1.7/0.8 como tu setup actual
    base_exec = dict(
        tp_atr_mult=1.7,
        sl_atr_mult=0.8,
        commission_pct=cfg.exec.commission_pct,
        slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
    )

    grid = [
        # (trail_atr_mult, trail_activation_atr, break_even_atr)
        (0.6, 0.6, 0.9),
        (0.6, 0.6, 0.8),
        (0.7, 0.6, 0.9),
        (0.7, 0.6, 0.8),
        (0.8, 0.6, 0.9),
        (0.8, 0.6, 0.8),
        (0.9, 0.6, 0.9),
        (0.9, 0.6, 0.8),
        # referencia actual
        (0.8, 0.5, 1.0),
    ]

    out = []
    rep = Path(cfg.reports_dir); rep.mkdir(parents=True, exist_ok=True)
    for tr, act, be in grid:
        exec_cfg = dict(base_exec, trail_atr_mult=tr, trail_activation_atr=act, break_even_atr=be)
        trades = run_backtest(sig, h1_map, d1_map, exec_cfg)
        met = kpis(trades); met.update({"trail_atr_mult": tr, "trail_activation_atr": act, "break_even_atr": be})
        out.append(met)
        print(met)

    df = pd.DataFrame(out).sort_values(["PnL_sum","Sharpe"], ascending=[False, False])
    df.to_csv(rep/"trail_tune_summary.csv", index=False)
    print("✅ Trail tuning listo → reports/trail_tune_summary.csv")
