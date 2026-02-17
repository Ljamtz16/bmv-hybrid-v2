# scripts/06_backtest_eval.py
from __future__ import annotations

import os
import re
import json
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals
from src.execution.hybrid_v2 import execute_hybrid_v2


# ------------------------------------------------------------
# Utils
# ------------------------------------------------------------

def month_span(ym: str) -> tuple[str, str]:
    """'YYYY-MM' -> (YYYY-MM-01, 1er día del mes siguiente)"""
    start = pd.Timestamp(ym + "-01")
    end = (start + pd.offsets.MonthBegin(1))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def first_available_ticker(d1_map: dict, tickers: list[str]) -> str | None:
    for t in tickers:
        if t in d1_map and d1_map[t] is not None and not d1_map[t].empty:
            return t
    return None

def ensure_atr_aliases_inplace(d1_map: dict[str, pd.DataFrame]) -> None:
    """Garantiza que existan ambas columnas ATR14 y ATR_14 en cada DF."""
    for t, df in d1_map.items():
        if df is None or df.empty:
            continue
        df2 = ensure_atr_14(df)  # asegura ATR (y crea alias si falta)
        if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
            df2["ATR_14"] = df2["ATR14"]
        if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
            df2["ATR14"] = df2["ATR_14"]
        d1_map[t] = df2

def pick_eval_dates(d1_map: dict[str, pd.DataFrame],
                    tickers: list[str],
                    start_s: str,
                    end_s: str) -> list[pd.Timestamp]:
    """Usa el primer ticker con datos para construir el índice de evaluación."""
    anchor = first_available_ticker(d1_map, tickers)
    if anchor is None:
        raise RuntimeError("No hay datos diarios en d1_map para ningún ticker.")
    idx = d1_map[anchor].index
    start = pd.Timestamp(start_s)
    end = pd.Timestamp(end_s)
    return [d for d in idx if (start <= d < end)]

def discover_latest_forecast_meta() -> tuple[str | None, dict]:
    """
    Busca el forecast más reciente en reports/forecast/YYYY-MM/meta.json.
    Devuelve (ym, meta_dict) o (None, {}).
    """
    base = Path("reports/forecast")
    if not base.exists():
        return None, {}
    dirs = [d for d in base.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}", d.name)]
    if not dirs:
        return None, {}
    dirs.sort(key=lambda p: p.name)  # lexicográfico sirve por YYYY-MM
    last = dirs[-1]
    meta_path = last / "meta.json"
    if meta_path.exists():
        try:
            return last.name, json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return last.name, {}
    return last.name, {}

def resolve_eval_window(cfg, args) -> tuple[str, str, str]:
    """
    Determina (start, end, source_tag) en este orden de prioridad:
    1) --start/--end explícitos
    2) --month (usa meta.json si existe; si no, month_span)
    3) ENV: BACKTEST_START/BACKTEST_END
    4) ENV: RUN_MONTH o FORECAST_MONTH (usa meta.json o month_span)
    5) Último forecast meta encontrado en reports/forecast/<YYYY-MM>/meta.json
    6) cfg.evaluation.start/end
    """
    # 1) start/end explícitos
    if args.start and args.end:
        return args.start, args.end, "args:start_end"

    # 2) --month
    if args.month:
        ym = args.month
        meta_path = Path("reports/forecast") / ym / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                return meta.get("eval_start"), meta.get("eval_end"), f"meta:{ym}"
            except Exception:
                pass
        s, e = month_span(ym)
        return s, e, f"month_span:{ym}"

    # 3) ENV start/end
    env_s = os.environ.get("BACKTEST_START")
    env_e = os.environ.get("BACKTEST_END")
    if env_s and env_e:
        return env_s, env_e, "env:BACKTEST_START_END"

    # 4) ENV month
    env_m = os.environ.get("RUN_MONTH") or os.environ.get("FORECAST_MONTH")
    if env_m:
        meta_path = Path("reports/forecast") / env_m / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                return meta.get("eval_start"), meta.get("eval_end"), f"env_meta:{env_m}"
            except Exception:
                pass
        s, e = month_span(env_m)
        return s, e, f"env_month_span:{env_m}"

    # 5) último forecast
    ym_last, meta = discover_latest_forecast_meta()
    if ym_last:
        if meta.get("eval_start") and meta.get("eval_end"):
            return meta["eval_start"], meta["eval_end"], f"latest_meta:{ym_last}"
        s, e = month_span(ym_last)
        return s, e, f"latest_month_span:{ym_last}"

    # 6) fallback config
    return cfg.evaluation["start"], cfg.evaluation["end"], "cfg:evaluation"

def run_backtest(sig_df: pd.DataFrame,
                 h1_map: dict[str, pd.DataFrame],
                 d1_map: dict[str, pd.DataFrame],
                 exec_cfg: dict) -> pd.DataFrame:
    """
    Ejecuta cada señal con execute_hybrid_v2 y devuelve un DataFrame de trades.
    Espera columnas: ['ticker','date','side','prob'] (al menos).
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

def kpis_by_side(trades_df: pd.DataFrame) -> pd.DataFrame:
    g = trades_df.groupby("side")["pnl"].agg(["count", "sum", "mean"]).copy()
    g["WinRate_%"] = trades_df.groupby("side")["pnl"].apply(lambda x: (x > 0).mean() * 100.0)
    return g

def overall_kpis(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {"Trades": 0, "WinRate_%": 0.0, "PnL_sum": 0.0}
    trades = int(trades_df.shape[0])
    winrate = float(round((trades_df["pnl"] > 0).mean() * 100.0, 2))
    pnl_sum = float(round(trades_df["pnl"].sum(), 2))
    return {"Trades": trades, "WinRate_%": winrate, "PnL_sum": pnl_sum}

def extra_metrics_and_exports(trades_df: pd.DataFrame, out_dir: Path) -> None:
    """
    Calcula equity, MDD, Sharpe aprox, expectancy, breakdowns, y exporta CSVs.
    """
    if trades_df.empty:
        print("\n⚠️ No hay trades para métricas extra.")
        return

    trades_df = trades_df.copy()
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values("date")

    # Equity curve
    trades_df["equity"] = trades_df["pnl"].cumsum()

    def max_drawdown(equity: pd.Series):
        roll_max = equity.cummax()
        drawdown = equity - roll_max
        mdd = drawdown.min()
        return float(-mdd), drawdown

    mdd, _ = max_drawdown(trades_df["equity"])

    # Sharpe anualizado aproximado (si pnl es por trade)
    ret = trades_df["pnl"]
    sharpe = ret.mean() / (ret.std(ddof=1) + 1e-12) * np.sqrt(252)
    expectancy = float(ret.mean())

    # Breakdown por razón
    by_reason = trades_df["reason"].value_counts().rename_axis("reason").reset_index(name="count")

    # Breakdown mensual (usar 'ME' para evitar FutureWarning)
    monthly = trades_df.groupby(pd.Grouper(key="date", freq="ME")).agg(
        trades=("pnl", "count"),
        pnl_sum=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100.0),
    )
    monthly.index = monthly.index.strftime("%Y-%m")
    monthly = monthly.reset_index().rename(columns={"date": "month"})

    # Por ticker
    by_ticker = trades_df.groupby("ticker").agg(
        trades=("pnl", "count"),
        pnl_sum=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100.0),
    ).reset_index().sort_values("pnl_sum", ascending=False)

    # Guardar
    out_dir.mkdir(exist_ok=True, parents=True)
    trades_df.to_csv(out_dir / "backtest_trades.csv", index=False)
    monthly.to_csv(out_dir / "backtest_monthly.csv", index=False)
    by_ticker.to_csv(out_dir / "backtest_by_ticker.csv", index=False)
    by_reason.to_csv(out_dir / "backtest_by_reason.csv", index=False)

    print("\n=== Métricas extra ===")
    print(f"Max Drawdown: {mdd:.2f}")
    print(f"Sharpe (aprox): {sharpe:.2f}")
    print(f"Expectancy por trade: {expectancy:.2f}")

    print("\n=== Breakdown por razón ===")
    print(by_reason)

    print("\n=== Mensual ===")
    print(monthly.tail(12))

    print("\n=== Por ticker (top 10) ===")
    print(by_ticker.head(10))


# ------------------------------------------------------------
# BUY gate helpers (auto/on/off) + auditoría
# ------------------------------------------------------------

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

def audit_buy_blocking(sig_all: pd.DataFrame, sig_used: pd.DataFrame, reports_dir: Path) -> pd.DataFrame:
    """
    Crea un resumen por ticker con:
      total_buy, kept_buy, blocked_buy, blocked_pct
    y lo guarda en <reports_dir>/buy_gate_usage_eval.csv
    """
    if sig_all is None or sig_all.empty:
        return pd.DataFrame(columns=["ticker","total_buy","kept_buy","blocked_buy","blocked_pct"])

    all_buy = sig_all[sig_all["side"] == "BUY"].copy()
    kept_buy = sig_used[sig_used["side"] == "BUY"].copy()

    g_all = all_buy.groupby("ticker").size().rename("total_buy").reset_index()
    g_keep = kept_buy.groupby("ticker").size().rename("kept_buy").reset_index()

    df = pd.merge(g_all, g_keep, on="ticker", how="left").fillna(0)
    df["kept_buy"] = df["kept_buy"].astype(int)
    df["blocked_buy"] = df["total_buy"].astype(int) - df["kept_buy"]
    df["blocked_pct"] = np.where(df["total_buy"] > 0, df["blocked_buy"] / df["total_buy"], 0.0)

    reports_dir.mkdir(parents=True, exist_ok=True)
    df.sort_values(["blocked_pct","blocked_buy"], ascending=[False, False]).to_csv(
        reports_dir / "buy_gate_usage_eval.csv", index=False
    )
    return df

def run_full(sig: pd.DataFrame,
             h1_map,
             d1_map,
             exec_cfg: dict,
             reports_dir: Path,
             tag: str):
    trades = run_backtest(sig, h1_map, d1_map, exec_cfg)
    kpis = overall_kpis(trades)
    # métrica secundaria por si empatan en PnL
    if trades.empty:
        sharpe = 0.0
    else:
        ret = trades["pnl"]
        sharpe = (ret.mean() / (ret.std(ddof=1) + 1e-12)) * np.sqrt(252)
    kpis["_Sharpe"] = float(sharpe)
    # guarda señales y trades con sufijo
    reports_dir.mkdir(parents=True, exist_ok=True)
    sig.to_csv(reports_dir / f"signals_eval_{tag}.csv", index=False)
    trades.to_csv(reports_dir / f"backtest_trades_{tag}.csv", index=False)
    return trades, kpis


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Backtest extendido alineado al mes/ventana solicitada.")
    p.add_argument("--cfg", default="config/paper.yaml", help="YAML de config (default: config/paper.yaml)")
    p.add_argument("--month", help="Mes a evaluar (YYYY-MM). Si existe meta.json se usa su ventana.")
    p.add_argument("--start", help="Inicio explícito YYYY-MM-DD (tiene prioridad sobre --month).")
    p.add_argument("--end", help="Fin exclusivo YYYY-MM-DD (tiene prioridad sobre --month).")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    cfg = load_cfg(args.cfg)

    # Sesión → tag (si lo usas)
    sH, eH = cfg.session.split("-")
    session_tag = f"{sH.replace(':','')}_{eH.replace(':','')}"

    # ---------- Resolver ventana ----------
    eval_start, eval_end, src = resolve_eval_window(cfg, args)
    # tag de salida: usa mes si lo tenemos, si no, el rango
    out_tag = args.month if args.month else f"{eval_start}__{eval_end}"
    print(f"\n🗓️ Ventana elegida: [{eval_start} → {eval_end})  (origen: {src})")

    # Cargar datos
    aliases = getattr(cfg, "aliases", None)
    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=session_tag, debug=False)

    # Asegurar ATR en diarios (ATR14 y ATR_14)
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

    # τ* global (fallback)
    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))

    # === Cargar thresholds por ticker (si existen) ===
    tau_by_ticker: dict = {}
    thr_path = "models/thresholds_by_ticker.json"
    if os.path.exists(thr_path):
        with open(thr_path, "r", encoding="utf-8") as f:
            tau_by_ticker = json.load(f)

    def tau_for(ticker: str, default_buy: float, default_sell: float) -> tuple[float, float]:
        t = tau_by_ticker.get(ticker, {})
        return float(t.get("BUY", default_buy)), float(t.get("SELL", default_sell))

    # Fechas de evaluación
    dates_eval = pick_eval_dates(d1_map, cfg.tickers, eval_start, eval_end)
    if not dates_eval:
        raise RuntimeError(f"No hay fechas de evaluación entre {eval_start} y {eval_end}.")

    # Generar señales por ticker usando τ por ticker (o global si falta)
    weights = (0.5, 0.3, 0.2)
    sig_list = []
    for t in cfg.tickers:
        if t not in d1_map or d1_map[t].empty:
            continue
        t_buy, t_sell = tau_for(t, tau_global_buy, tau_global_sell)
        sig_t = generate_daily_signals({t: d1_map[t]}, rf, svm, lstm, t_buy, t_sell, [t], dates_eval, weights)
        if sig_t is not None and not sig_t.empty:
            sig_list.append(sig_t)

    sig = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker", "date", "side", "prob"])

    # Ejecutar backtest (config de ejecución)
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

    # Directorio de salida por ventana
    base_reports = Path(getattr(cfg, "reports_dir", "reports"))
    reports_dir = base_reports / "backtests" / out_tag
    reports_dir.mkdir(parents=True, exist_ok=True)

    # === BUY gate policy ===
    buy_gate_path = Path("models/buy_gate.json")
    buy_gate = load_buy_gate(buy_gate_path)

    signals_cfg = getattr(cfg, "signals", {}) or {}
    apply_mode = str(signals_cfg.get("apply_buy_gate", "auto")).lower()  # 'auto'|'true'|'false'

    # También auditamos el bloqueo BUY por ticker
    audit_df = None

    if apply_mode == "false" or not buy_gate:
        # No gate
        sig_used = sig.copy()
        trades_df, picked = run_full(sig_used, h1_map, d1_map, exec_cfg, reports_dir, "no_gate")
        print("\n🔎 Modo: SIN BUY gate (forzado o no hay json).")

    elif apply_mode == "true":
        # Gate forzado
        sig_used = apply_buy_gate(sig, buy_gate)
        trades_df, picked = run_full(sig_used, h1_map, d1_map, exec_cfg, reports_dir, "with_gate")
        print("\n🔒 Modo: CON BUY gate (forzado).")
        # Auditoría de bloqueos
        audit_df = audit_buy_blocking(sig, sig_used, reports_dir)

    else:
        # AUTO: comparar ambas variantes y elegir
        sig_no = sig.copy()
        sig_yes = apply_buy_gate(sig, buy_gate)

        trades_no, k_no = run_full(sig_no,  h1_map, d1_map, exec_cfg, reports_dir, "no_gate")
        trades_yes, k_yes = run_full(sig_yes, h1_map, d1_map, exec_cfg, reports_dir, "with_gate")

        # criterio: mayor PnL_sum; si empata, mayor Sharpe
        key = "PnL_sum"
        better = "with_gate" if (k_yes[key] > k_no[key] or (k_yes[key] == k_no[key] and k_yes["_Sharpe"] > k_no["_Sharpe"])) else "no_gate"
        if better == "with_gate":
            sig_used, trades_df, picked = sig_yes, trades_yes, k_yes
            print("\n🤖 AUTO: elegí CON BUY gate (mejor PnL/Sharpe).")
            audit_df = audit_buy_blocking(sig, sig_used, reports_dir)
        else:
            sig_used, trades_df, picked = sig_no, trades_no, k_no
            print("\n🤖 AUTO: elegí SIN BUY gate (mejor PnL/Sharpe).")

    # KPIs impresos (usando trades_df ya elegido)
    if trades_df.empty:
        print("⚠️ No se generaron trades en el periodo de evaluación.")
    else:
        kpis_side = kpis_by_side(trades_df)
        print("\n=== KPIs por lado ===")
        print(kpis_side)

        total = overall_kpis(trades_df)
        print("\n=== Total ===\n", total)

    # Export y métricas extra del conjunto elegido
    extra_metrics_and_exports(trades_df, reports_dir)

    # Resumen rápido de la auditoría de bloqueos
    if audit_df is not None and not audit_df.empty:
        top_blocked = audit_df.sort_values(["blocked_pct","blocked_buy"], ascending=[False, False]).head(10)
        print("\n=== Auditoría BUY gate (top bloqueados) ===")
        print(top_blocked)

    # Guardar meta del backtest
    meta = {
        "source_window": src,
        "eval_start": eval_start,
        "eval_end": eval_end,
        "out_tag": out_tag,
        "reports_dir": str(reports_dir),
    }
    (reports_dir / "meta_backtest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\n✅ Backtest completado. Carpeta: {reports_dir}")
    print("Archivos: backtest_trades.csv, backtest_monthly.csv, backtest_by_ticker.csv, backtest_by_reason.csv")
