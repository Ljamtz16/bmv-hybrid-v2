# scripts/07b_validate_top_configs.py
from __future__ import annotations

import os, json, argparse, re
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

# ---------------------------- Utils base (copias ligeras) ----------------------------

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
    """'YYYY-MM' -> (primer día del mes, primer día del mes siguiente)"""
    y, m = map(int, ym.split("-"))
    start = pd.Timestamp(year=y, month=m, day=1)
    end = start + pd.offsets.MonthBegin(1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

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

# ---------------------------- Parseo de run_tag del barrido ----------------------------

RUN_TAG_RE = re.compile(
    r"""^(?P<month>\d{4}-\d{2})_tp(?P<tp>[\d.]+)_sl(?P<sl>[\d.]+)_tr(?P<tr>[\d.]+)_act(?P<act>[\d.]+)_be(?P<be>[\d.]+)_(?P<gate>auto|true|false)""",
    re.IGNORECASE,
)

def parse_run_tag(tag: str) -> dict | None:
    m = RUN_TAG_RE.match(tag)
    if not m:
        return None
    d = m.groupdict()
    d["tp"] = float(d["tp"]); d["sl"] = float(d["sl"]); d["tr"] = float(d["tr"])
    d["act"] = float(d["act"]); d["be"] = float(d["be"])
    d["gate"] = d["gate"].lower()
    return d

# ---------------------------- Validación para una config en varios meses ----------------------------

def validate_config_over_months(cfg_base,
                                run_cfg: dict,
                                months: list[str],
                                dump_dir: Path | None = None) -> pd.DataFrame:
    """
    run_cfg = dict(tp, sl, tr, act, be, gate)
    months = ['2024-10','2024-11', ...]
    """
    # Datos comunes
    cfg = cfg_base
    sH, eH = cfg.session.split("-")
    tag_session = f"{sH.replace(':','')}_{eH.replace(':','')}"
    aliases = getattr(cfg, "aliases", None)

    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag_session, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # τ global + thresholds por ticker (si existen)
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

    # buy gate (si aplica)
    buy_gate = load_buy_gate(Path("models/buy_gate.json"))

    # Exec override
    exec_cfg = dict(
        tp_atr_mult=run_cfg["tp"],
        sl_atr_mult=run_cfg["sl"],
        trail_atr_mult=run_cfg["tr"],
        trail_activation_atr=run_cfg["act"],
        break_even_atr=run_cfg["be"],
        commission_pct=cfg.exec.commission_pct,
        slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
    )

    rows = []
    for ym in months:
        eval_start, eval_end = month_span(ym)

        # señales
        dates_eval = pick_eval_dates(d1_map, cfg.tickers, eval_start, eval_end)
        if not dates_eval:
            rows.append({"run_tag": "", "month": ym, "error": f"Sin fechas {eval_start}~{eval_end}"})
            continue

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

        gate_mode = run_cfg["gate"]
        if gate_mode == "true":
            sig_used = apply_buy_gate(sig, buy_gate); gate_tag = "gateOn"
        elif gate_mode == "false":
            sig_used = sig.copy(); gate_tag = "gateOff"
        else:
            # auto: comparar
            sig_no = sig.copy()
            sig_yes = apply_buy_gate(sig, buy_gate)
            trades_no = run_backtest(sig_no,  h1_map, d1_map, exec_cfg)
            trades_yes = run_backtest(sig_yes, h1_map, d1_map, exec_cfg)
            k_no = kpis(trades_no); k_yes = kpis(trades_yes)
            pick_with = (k_yes["PnL_sum"] > k_no["PnL_sum"]) or (k_yes["PnL_sum"] == k_no["PnL_sum"] and k_yes["Sharpe"] > k_no["Sharpe"])
            sig_used = sig_yes if pick_with else sig_no
            gate_tag = "gateAutoYes" if pick_with else "gateAutoNo"

        trades = run_backtest(sig_used, h1_map, d1_map, exec_cfg)
        kp = kpis(trades)
        kp.update(dict(month=ym, buy_gate=gate_tag,
                       tp_atr_mult=exec_cfg["tp_atr_mult"], sl_atr_mult=exec_cfg["sl_atr_mult"],
                       trail_atr_mult=exec_cfg["trail_atr_mult"], trail_activation_atr=exec_cfg["trail_activation_atr"],
                       break_even_atr=exec_cfg["break_even_atr"]))
        rows.append(kp)

        if dump_dir:
            dump_dir.mkdir(parents=True, exist_ok=True)
            trades.to_csv(dump_dir / f"trades_{ym}.csv", index=False)

    return pd.DataFrame(rows)

# ---------------------------- CLI ----------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Valida las Top-N configuraciones de param_sweep_summary.csv en múltiples meses."
    )
    p.add_argument("--summary", type=str, default="reports/param_sweep/param_sweep_summary.csv",
                   help="Ruta al resumen del barrido")
    p.add_argument("--top_n", type=int, default=3, help="Cuántas configuraciones del top validar")
    p.add_argument("--months", type=str, default="2024-10,2024-11,2024-12,2025-01",
                   help="Meses a validar separados por coma (YYYY-MM)")
    p.add_argument("--out", type=str, default="reports/param_sweep/topN_validation.csv",
                   help="Ruta de salida CSV")
    p.add_argument("--dump_runs", action="store_true",
                   help="Guardar trades por mes y por configuración")
    return p.parse_args()

# ---------------------------- Main ----------------------------

if __name__ == "__main__":
    args = parse_args()
    cfg = load_cfg("config/base.yaml")

    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise FileNotFoundError(f"No encontré el archivo de resumen: {summary_path}")

    df = pd.read_csv(summary_path)
    if "run_tag" not in df.columns:
        raise ValueError("El resumen no contiene columna 'run_tag'.")

    # Ordenamos (si no viene ya)
    sort_cols = [c for c in ["PnL_sum", "Sharpe"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False]*len(sort_cols))

    top = df.head(args.top_n)["run_tag"].tolist()
    months = [m.strip() for m in args.months.split(",") if m.strip()]

    out_rows = []
    for i, tag in enumerate(top, 1):
        parsed = parse_run_tag(tag)
        if parsed is None:
            print(f"⚠️ No pude parsear run_tag: {tag} — lo salto.")
            continue
        print(f"[{i}] Validando: {tag}")
        run_cfg = dict(tp=parsed["tp"], sl=parsed["sl"], tr=parsed["tr"],
                       act=parsed["act"], be=parsed["be"], gate=parsed["gate"])
        dump_dir = (Path("reports/param_sweep/topN_runs") / f"{i}_{tag}") if args.dump_runs else None
        res_df = validate_config_over_months(cfg, run_cfg, months, dump_dir)
        res_df.insert(0, "rank", i)
        res_df.insert(1, "run_tag", tag)
        out_rows.append(res_df)

    final = pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame(
        columns=["rank","run_tag","month","Trades","WinRate_%","PnL_sum","MDD","Sharpe","Expectancy",
                 "buy_gate","tp_atr_mult","sl_atr_mult","trail_atr_mult","trail_activation_atr","break_even_atr"]
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n✅ Validación terminada. Resultados → {out_path}")
    if args.dump_runs:
        print("ℹ️ Dumps de trades por corrida en reports/param_sweep/topN_runs/")
