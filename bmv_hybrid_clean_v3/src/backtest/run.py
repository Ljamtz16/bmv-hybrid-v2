import os, json, pandas as pd
from ..config import load_cfg
from ..io.loader import load_daily_map, load_hourly_map
from ..features.indicators import ensure_atr_14
from ..models.adapters import LSTMSim
from ..signals.generate import generate_daily_signals
from ..calibrate.threshold import scan_tau_pnl
from ..execution.hybrid_v2 import execute_hybrid_v2

def search_weights(d1_map, cfg, step=0.1):
    vals = [round(i*step,10) for i in range(int(1/step)+1)]
    for a in vals:
        for b in vals:
            c = round(1.0 - a - b, 10)
            if c < -1e-9: continue
            if c < 0: c = 0.0
            if abs(a+b+c-1.0) <= 1e-8: yield (float(a),float(b),float(c))

def main():
    cfg = load_cfg("config/base.yaml")
    os.makedirs(cfg.reports_dir, exist_ok=True)
    # Load data
    d1_map = load_daily_map(os.path.join(cfg.data_dir,"raw","1d"), cfg.tickers)
    for t in d1_map: d1_map[t] = ensure_atr_14(d1_map[t])
    sH,eH = cfg.session.split("-"); tag = f"{sH.replace(':','')}_{eH.replace(':','')}"
    h1_map = load_hourly_map(os.path.join(cfg.data_dir,"raw","1h"), cfg.tickers, session_tag=tag)

    # Models (optional)
    rf = svm = None
    try:
        import joblib
        if os.path.exists(cfg.models["rf_path"]): rf = joblib.load(cfg.models["rf_path"])
        if os.path.exists(cfg.models["svm_path"]): svm = joblib.load(cfg.models["svm_path"])
    except Exception as e:
        print("⚠️ No RF/SVM:", e)
    lstm = LSTMSim()

    # Calibration period
    cal_start = pd.Timestamp(cfg.calibration["start"]); cal_end = pd.Timestamp(cfg.calibration["end"])
    dates_cal = [d for d in d1_map[cfg.tickers[0]].index if (cal_start <= d < cal_end)]

    # Execution config
    exec_cfg = dict(
        tp_atr_mult=cfg.exec.tp_atr_mult, sl_atr_mult=cfg.exec.sl_atr_mult,
        commission_pct=cfg.exec.commission_pct, slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
        trail_atr_mult=cfg.exec.trail_atr_mult,
        trail_activation_atr=cfg.exec.trail_activation_atr,
        break_even_atr=cfg.exec.break_even_atr
    )
    tau_grid = cfg.calibration["tau_grid"]

    # Search fusion weights
    best = None; best_score = -1e18
    for w in search_weights(d1_map, cfg, step=cfg.calibration.get("fusion_step",0.1)):
        sig = generate_daily_signals(d1_map, rf, svm, lstm, 0.0, 0.0, cfg.tickers, dates_cal, weights=w)
        if sig.empty: continue
        tb, pb, _ = scan_tau_pnl(sig, "BUY", h1_map, d1_map, tau_grid, exec_cfg)
        ts, ps, _ = scan_tau_pnl(sig, "SELL", h1_map, d1_map, tau_grid, exec_cfg)
        total = (pb or 0) + (ps or 0)
        if total > best_score:
            best_score = total
            best = {"weights": w, "tau_buy": tb, "tau_sell": ts, "pnl_total": total}

    if not best:
        print("❌ Sin señales en calibración")
        return

    print(f"⭐ Pesos óptimos: {best['weights']} | τ* BUY={best['tau_buy']} SELL={best['tau_sell']} | PnL cal={best['pnl_total']:.2f}")
    with open("models/fusion_weights.json","w",encoding="utf-8") as f:
        json.dump({"weights": best["weights"]}, f, indent=2)
    with open("models/thresholds.json","w",encoding="utf-8") as f:
        json.dump({"buy": best['tau_buy'], "sell": best['tau_sell']}, f, indent=2)

    # Evaluation
    ev_start = pd.Timestamp(cfg.evaluation["start"]); ev_end = pd.Timestamp(cfg.evaluation["end"])
    dates_ev = [d for d in d1_map[cfg.tickers[0]].index if (ev_start <= d < ev_end)]

    sig_ev = generate_daily_signals(d1_map, rf, svm, lstm,
                                    buy_tau=best["tau_buy"], sell_tau=best["tau_sell"],
                                    tickers=cfg.tickers, dates=dates_ev, weights=tuple(best["weights"]))
    sig_ev.to_csv(os.path.join(cfg.reports_dir,"signals_eval.csv"), index=False)

    trades = []
    for _, s in sig_ev.iterrows():
        res = execute_hybrid_v2(
            h1_map, d1_map, s["ticker"], s["date"], s["side"], s["prob"],
            tp_mult=cfg.exec.tp_atr_mult, sl_mult=cfg.exec.sl_atr_mult,
            commission=cfg.exec.commission_pct, slippage=cfg.exec.slippage_pct,
            max_holding_days=cfg.exec.max_holding_days,
            trail_atr_mult=cfg.exec.trail_atr_mult,
            trail_activation_atr=cfg.exec.trail_activation_atr,
            break_even_atr=cfg.exec.break_even_atr
        )
        trades.append(res)
    trades_df = pd.DataFrame(trades)
    trades_df.to_csv(os.path.join(cfg.reports_dir,"trades_eval.csv"), index=False)

    if not trades_df.empty:
        trades_df["win"] = trades_df["pnl"] > 0
        by_side = trades_df.groupby("side")["pnl"].agg(["count","sum","mean"]).copy()
        by_side["WinRate_%"] = trades_df.groupby("side")["win"].mean()*100
        by_side.to_csv(os.path.join(cfg.reports_dir,"summary_by_side.csv"))
        total = {"Trades": int(len(trades_df)),
                 "WinRate_%": round(float(trades_df["win"].mean()*100),2),
                 "PnL_sum": round(float(trades_df["pnl"].sum()),2)}
        pd.DataFrame([total]).to_csv(os.path.join(cfg.reports_dir,"summary_total.csv"), index=False)
        print("\n=== KPIs por lado ===\n", by_side)
        print("\n=== Total ===\n", total)
    else:
        print("No hubo operaciones en evaluación. Revisa τ/pesos o señales.")

if __name__ == "__main__":
    main()
