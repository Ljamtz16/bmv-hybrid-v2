# scripts/07_param_sweep_eval.py
from __future__ import annotations

import os, json, argparse
from pathlib import Path
from copy import deepcopy
import pandas as pd
import numpy as np

from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals
from src.execution.hybrid_v2 import execute_hybrid_v2
from src.calibrate.threshold import scan_tau_pnl  # <-- para recalibrar τ

# ---------------------------- Utils base ----------------------------

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

def first_available_ticker(d1_map: dict, tickers: list[str]) -> str | None:
    for t in tickers:
        if t in d1_map and d1_map[t] is not None and not d1_map[t].empty:
            return t
    return None

def pick_eval_dates(d1_map: dict[str, pd.DataFrame], tickers: list[str], start_s: str, end_s: str):
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
    return {"Trades": t, "WinRate_%": round(winrate, 2), "PnL_sum": round(pnl_sum, 2),
            "MDD": round(mdd, 2), "Sharpe": round(sharpe, 2), "Expectancy": round(expectancy, 2)}

def month_span(ym: str) -> tuple[str, str]:
    """'YYYY-MM' -> (primer día del mes, primer día del mes siguiente) en formato YYYY-MM-DD."""
    y, m = map(int, ym.split("-"))
    start = pd.Timestamp(year=y, month=m, day=1)
    end = start + pd.offsets.MonthBegin(1)  # primer día del mes siguiente
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def lookback_span(ym: str, k: int) -> tuple[str, str, str, str]:
    """
    Para un mes 'ym' (ej. '2024-11'), devuelve:
      cal_start, cal_end  -> [incl, excl): k meses previos al mes objetivo
      eval_start, eval_end -> [incl, excl): el mes objetivo
    """
    eval_start_s, eval_end_s = month_span(ym)
    eval_start = pd.Timestamp(eval_start_s)
    cal_end = eval_start  # excluyente
    cal_start = cal_end - pd.offsets.MonthBegin(k)
    return (cal_start.strftime("%Y-%m-%d"),
            cal_end.strftime("%Y-%m-%d"),
            eval_start_s,
            eval_end_s)

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

# ---------------------------- Calibración en ventana previa ----------------------------

def calibrate_tau_by_ticker_in_window(cfg,
                                      d1_map, h1_map,
                                      cal_start: str, cal_end: str,
                                      weights=(0.5, 0.3, 0.2)) -> dict[str, dict]:
    """
    Recalibra τ por ticker en la ventana [cal_start, cal_end), usando scan_tau_pnl.
    Devuelve: {ticker: {"BUY": τb, "SELL": τs}}
    """
    # modelos
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

    grid = getattr(cfg, "calibration", {}).get("tau_grid", [0.45, 0.5, 0.55, 0.6, 0.65])
    exec_cfg = dict(
        tp_atr_mult=cfg.exec.tp_atr_mult, sl_atr_mult=cfg.exec.sl_atr_mult,
        commission_pct=cfg.exec.commission_pct, slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
        trail_atr_mult=cfg.exec.trail_atr_mult,
        trail_activation_atr=cfg.exec.trail_activation_atr,
        break_even_atr=cfg.exec.break_even_atr
    )

    dates_cal = pick_eval_dates(d1_map, cfg.tickers, cal_start, cal_end)
    tau_by_ticker: dict[str, dict] = {}
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        # señales sin τ (0.0) para barrer luego
        sig_t = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, 0.0, 0.0, [t], dates_cal, weights)
        if sig_t is None or sig_t.empty:
            continue
        tau_buy, _, _ = scan_tau_pnl(sig_t, "BUY",  h1_map, d1_map, grid, exec_cfg)
        tau_sell, _, _ = scan_tau_pnl(sig_t, "SELL", h1_map, d1_map, grid, exec_cfg)
        tau_by_ticker[t] = {"BUY": float(tau_buy), "SELL": float(tau_sell)}
    return tau_by_ticker

def build_buy_gate_in_window(cfg,
                             d1_map, h1_map,
                             cal_start: str, cal_end: str,
                             tau_by_ticker: dict[str, dict] | None,
                             min_trades: int = 6,
                             expect_min: float = 0.0,
                             weights=(0.5, 0.3, 0.2)) -> dict[str, bool]:
    """
    Construye un buy gate por ticker a partir de desempeño BUY en la ventana previa.
    Habilita BUY si expectancy>=expect_min y trades>=min_trades.
    """
    # modelos
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

    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))

    def tau_for(ticker: str) -> tuple[float, float]:
        if tau_by_ticker and ticker in tau_by_ticker:
            t = tau_by_ticker[ticker]
            return float(t.get("BUY", tau_global_buy)), float(t.get("SELL", tau_global_sell))
        return tau_global_buy, tau_global_sell

    dates_cal = pick_eval_dates(d1_map, cfg.tickers, cal_start, cal_end)
    exec_cfg = dict(
        tp_atr_mult=cfg.exec.tp_atr_mult, sl_atr_mult=cfg.exec.sl_atr_mult,
        commission_pct=cfg.exec.commission_pct, slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
        trail_atr_mult=cfg.exec.trail_atr_mult,
        trail_activation_atr=cfg.exec.trail_activation_atr,
        break_even_atr=cfg.exec.break_even_atr
    )

    gate: dict[str, bool] = {}
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        tb, ts = tau_for(t)
        sig_t = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, tb, ts, [t], dates_cal, weights)
        if sig_t is None or sig_t.empty:
            gate[t] = True  # sin señales → no bloquear
            continue
        # quedarnos con BUY
        sig_buy = sig_t.loc[sig_t["side"] == "BUY"].reset_index(drop=True)
        if sig_buy.empty:
            gate[t] = True
            continue
        trades = run_backtest(sig_buy, h1_map, d1_map, exec_cfg)
        n = trades.shape[0]
        exp = trades["pnl"].mean() if n > 0 else 0.0
        gate[t] = (n >= min_trades) and (exp >= expect_min)
    return gate

# ---------------------------- Runner principal (una corrida) ----------------------------

def run_once(cfg_base,
             eval_start: str,
             eval_end: str,
             exec_override: dict,
             buy_gate_mode: str,
             dump_dir: Path | None = None,
             # nuevos toggles/lookback
             lookback_months: int = 12,
             use_lookback_tau: bool = False,
             use_lookback_gate: bool = False,
             gate_min_trades: int = 6,
             gate_expect_min: float = 0.0) -> dict:
    """
    buy_gate_mode: 'auto' | 'true' | 'false'
    exec_override: dict con claves de cfg.exec a modificar SOLO en memoria
    """

    # 1) Clonar config en memoria y aplicar override de exec
    cfg = deepcopy(cfg_base)
    for k, v in exec_override.items():
        setattr(cfg.exec, k, v)

    # 2) Datos
    sH, eH = cfg.session.split("-")
    tag_session = f"{sH.replace(':','')}_{eH.replace(':','')}"
    aliases = getattr(cfg, "aliases", None)

    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag_session, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # 3) τ global
    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))

    # 4) τ por ticker (por defecto desde archivo; opcional: recalibrar con lookback)
    tau_by_ticker: dict = {}
    thr_path = "models/thresholds_by_ticker.json"
    if os.path.exists(thr_path):
        with open(thr_path, "r", encoding="utf-8") as f:
            tau_by_ticker = json.load(f)

    if use_lookback_tau:
        # ventana previa
        cal_start, cal_end, _, _ = lookback_span(pd.Timestamp(eval_start).strftime("%Y-%m"))
        tau_by_ticker = calibrate_tau_by_ticker_in_window(cfg, d1_map, h1_map, cal_start, cal_end)

    def tau_for(ticker: str) -> tuple[float, float]:
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", tau_global_buy)), float(t.get("SELL", tau_global_sell))

    # 5) Señales en ventana de evaluación
    dates_eval = pick_eval_dates(d1_map, cfg.tickers, eval_start, eval_end)
    if not dates_eval:
        return {"error": f"Sin fechas entre {eval_start} y {eval_end}"}

    # modelos (para señales)
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

    weights = (0.5, 0.3, 0.2)
    sig_list = []
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        tb, ts = tau_for(t)
        sig_t = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, tb, ts, [t], dates_eval, weights)
        if sig_t is not None and not sig_t.empty:
            sig_list.append(sig_t)
    sig = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

    # 6) BUY gate (desde archivo o reconstruido con lookback)
    if use_lookback_gate:
        cal_start, cal_end, _, _ = lookback_span(pd.Timestamp(eval_start).strftime("%Y-%m"))
        buy_gate = build_buy_gate_in_window(cfg, d1_map, h1_map, cal_start, cal_end,
                                            tau_by_ticker,
                                            min_trades=gate_min_trades,
                                            expect_min=gate_expect_min,
                                            weights=weights)
    else:
        buy_gate = load_buy_gate(Path("models/buy_gate.json"))

    # 7) Ejecutar según modo de gate
    def run_variant(sig_df, tag_suffix):
        trades = run_backtest(sig_df, h1_map, d1_map, cfg.exec.__dict__)
        k = kpis(trades)
        if dump_dir:
            dump_dir.mkdir(parents=True, exist_ok=True)
            sig_df.to_csv(dump_dir / f"signals_{tag_suffix}.csv", index=False)
            trades.to_csv(dump_dir / f"trades_{tag_suffix}.csv", index=False)
        return trades, k

    if buy_gate_mode == "true":
        sig_used = apply_buy_gate(sig, buy_gate)
        trades, kp = run_variant(sig_used, "with_gate")
        gate_tag = "gateOn"
    elif buy_gate_mode == "false":
        sig_used = sig.copy()
        trades, kp = run_variant(sig_used, "no_gate")
        gate_tag = "gateOff"
    else:
        # auto
        trades_no, k_no = run_variant(sig.copy(), "no_gate")
        sig_yes = apply_buy_gate(sig, buy_gate)
        trades_yes, k_yes = run_variant(sig_yes, "with_gate")
        pick_with = (k_yes["PnL_sum"] > k_no["PnL_sum"]) or (k_yes["PnL_sum"] == k_no["PnL_sum"] and k_yes["Sharpe"] > k_no["Sharpe"])
        trades, kp = (trades_yes, k_yes) if pick_with else (trades_no, k_no)
        gate_tag = "gateAutoYes" if pick_with else "gateAutoNo"

    # 8) Meta/dumps
    if dump_dir:
        meta = {
            "eval_start": eval_start, "eval_end": eval_end,
            "exec": exec_override, "buy_gate_mode": buy_gate_mode, "gate_tag": gate_tag,
            "kpis": kp,
            "use_lookback_tau": use_lookback_tau,
            "use_lookback_gate": use_lookback_gate,
            "lookback_months": lookback_months
        }
        with (dump_dir / "meta.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    kp.update(dict(eval_start=eval_start, eval_end=eval_end, buy_gate=gate_tag))
    kp.update(exec_override)
    return kp

# ---------------------------- CLI & barrido ----------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Barrido de parámetros TP/SL/trailing y meses, con opción de lookback de 12m para τ y buy gate."
    )
    p.add_argument("--months", type=str, default="2024-01,2024-02,2024-03," \
    "2024-04,2024-05,2024-06,2024-07,2024-08,2024-09,2024-10,2024-11,2024-12,2025-01",
                   help="Meses separados por coma en formato YYYY-MM (ej: 2024-10,2024-11)")
    p.add_argument("--tp", type=str, default="1.5,1.6,1.7,1.8,1.9,2.0",
                   help="Lista de tp_atr_mult separados por coma (ej: 1.5,1.6,1.7)")
    p.add_argument("--sl", type=str, default="0.7,0.8,0.9",
                   help="Lista de sl_atr_mult separados por coma (ej: 0.7,0.8,0.9)")
    p.add_argument("--trail", type=str, default="0.6,0.7",
                   help="Lista de trail_atr_mult (ej: 0.0,0.6,0.7)")
    p.add_argument("--trail_act", type=str, default="0.6",
                   help="Lista de trail_activation_atr (ej: 0.5,0.6)")
    p.add_argument("--breakeven", type=str, default="0.8,1.0",
                   help="Lista de break_even_atr (ej: 0.8,1.0)")
    p.add_argument("--gate", type=str, default="auto,true,false",
                   help="Modos de buy gate a probar: auto,true,false (separados por coma)")
    p.add_argument("--dump", action="store_true",
                   help="Guardar señales y trades de cada corrida en reports/param_sweep/<run_tag>")

    # ---- NUEVO: lookback dinámico ----
    p.add_argument("--lookback_months", type=int, default=12,
                   help="Meses previos para calibración por ventana (default 12)")
    p.add_argument("--use_lookback_tau", action="store_true",
                   help="Recalibrar τ por ticker usando la ventana previa")
    p.add_argument("--use_lookback_gate", action="store_true",
                   help="Construir buy gate con la ventana previa (ignora models/buy_gate.json)")
    p.add_argument("--gate_min_trades", type=int, default=6,
                   help="Mínimo de trades BUY por ticker para habilitar BUY (si --use_lookback_gate)")
    p.add_argument("--gate_expect_min", type=float, default=0.0,
                   help="Expectancy mínima por ticker para habilitar BUY (si --use_lookback_gate)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    cfg = load_cfg("config/base.yaml")

    months = [m.strip() for m in args.months.split(",") if m.strip()]
    tps = [float(x) for x in args.tp.split(",") if x.strip()]
    sls = [float(x) for x in args.sl.split(",") if x.strip()]
    trails = [float(x) for x in args.trail.split(",") if x.strip()]
    trail_acts = [float(x) for x in args.trail_act.split(",") if x.strip()]
    breakevens = [float(x) for x in args.breakeven.split(",") if x.strip()]
    gates = [g.strip().lower() for g in args.gate.split(",") if g.strip()]

    reports_root = Path(cfg.reports_dir if hasattr(cfg, "reports_dir") else "reports")
    sweep_dir = reports_root / "param_sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    run_idx = 0
    for ym in months:
        # span de evaluación del mes objetivo
        eval_start, eval_end = month_span(ym)

        for tp in tps:
            for sl in sls:
                for tr in trails:
                    for ta in trail_acts:
                        for be in breakevens:
                            for gate_mode in gates:
                                exec_override = dict(
                                    tp_atr_mult=tp,
                                    sl_atr_mult=sl,
                                    trail_atr_mult=tr,
                                    trail_activation_atr=ta,
                                    break_even_atr=be,
                                    commission_pct=cfg.exec.commission_pct,
                                    slippage_pct=cfg.exec.slippage_pct,
                                    max_holding_days=cfg.exec.max_holding_days,
                                )
                                run_idx += 1
                                lbt = "lt" if args.use_lookback_tau else "nt"
                                lbg = "lg" if args.use_lookback_gate else "ng"
                                run_tag = f"{ym}_tp{tp}_sl{sl}_tr{tr}_act{ta}_be{be}_{gate_mode}_{lbt}_{lbg}"
                                print(f"[{run_idx}] {run_tag}")

                                dump_dir = (sweep_dir / run_tag) if args.dump else None
                                res = run_once(
                                    cfg,
                                    eval_start, eval_end,
                                    exec_override, gate_mode, dump_dir,
                                    lookback_months=args.lookback_months,
                                    use_lookback_tau=args.use_lookback_tau,
                                    use_lookback_gate=args.use_lookback_gate,
                                    gate_min_trades=args.gate_min_trades,
                                    gate_expect_min=args.gate_expect_min
                                )
                                res["run_tag"] = run_tag
                                rows.append(res)

    df = pd.DataFrame(rows)
    out_csv = sweep_dir / "param_sweep_summary.csv"
    df_cols = ["run_tag", "eval_start", "eval_end", "buy_gate",
               "tp_atr_mult", "sl_atr_mult", "trail_atr_mult", "trail_activation_atr", "break_even_atr",
               "Trades", "WinRate_%", "PnL_sum", "MDD", "Sharpe", "Expectancy"]
    if not df.empty:
        df = df[[c for c in df_cols if c in df.columns]].copy()
        df = df.sort_values(["PnL_sum", "Sharpe"], ascending=[False, False])
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n✅ Barrido completado. Resumen → {out_csv}")
    if args.dump:
        print("ℹ️ Se guardaron señales/trades de cada corrida en subcarpetas de reports/param_sweep/")
