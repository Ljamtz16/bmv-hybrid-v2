# scripts/05_1_calibrate_by_ticker_and_exec_scenarios.py
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
from src.calibrate.threshold import scan_tau_pnl
from src.execution.hybrid_v2 import execute_hybrid_v2

# ------------------------------ utils ---------------------------------

def ensure_atr_aliases_inplace(d1_map: dict[str, pd.DataFrame]) -> None:
    """Garantiza ATR14 y ATR_14 en cada DF diario (compatibilidad)."""
    for t, df in d1_map.items():
        if df is None or df.empty:
            continue
        df2 = ensure_atr_14(df)
        if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
            df2["ATR_14"] = df2["ATR14"]
        if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
            df2["ATR14"] = df2["ATR_14"]
        d1_map[t] = df2

def pick_dates_for_ticker(d1_map: dict[str, pd.DataFrame], t: str, start_s: str, end_s: str) -> list[pd.Timestamp]:
    if t not in d1_map or d1_map[t] is None or d1_map[t].empty:
        return []
    idx = d1_map[t].index
    start = pd.Timestamp(start_s)
    end = pd.Timestamp(end_s)
    return [d for d in idx if (start <= d < end)]

def run_backtest(sig_df: pd.DataFrame,
                 h1_map: dict[str, pd.DataFrame],
                 d1_map: dict[str, pd.DataFrame],
                 exec_cfg: dict) -> pd.DataFrame:
    """Ejecuta cada señal con execute_hybrid_v2 y devuelve DF de trades."""
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
    trades_df = trades_df.copy()
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values("date")
    # equity y MDD
    trades_df["equity"] = trades_df["pnl"].cumsum()
    roll_max = trades_df["equity"].cummax()
    drawdown = trades_df["equity"] - roll_max
    mdd = float(-(drawdown.min() if not drawdown.empty else 0.0))
    # sharpe aprox (por trade)
    ret = trades_df["pnl"]
    sharpe = float(ret.mean() / (ret.std(ddof=1) + 1e-12) * np.sqrt(252)) if len(ret) > 1 else 0.0
    # expectancy
    expectancy = float(ret.mean()) if not ret.empty else 0.0
    return {
        "Trades": int(trades_df.shape[0]),
        "WinRate_%": float(round((trades_df["pnl"] > 0).mean() * 100.0, 2)),
        "PnL_sum": float(round(trades_df["pnl"].sum(), 2)),
        "MDD": float(round(mdd, 2)),
        "Sharpe": float(round(sharpe, 2)),
        "Expectancy": float(round(expectancy, 2)),
    }

# ------------------------------ main ----------------------------------

if __name__ == "__main__":
    cfg = load_cfg("config/base.yaml")
    reports_dir = Path(cfg.reports_dir if hasattr(cfg, "reports_dir") else "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    Path("models").mkdir(exist_ok=True)

    # Sesión → tag (por compat con tu loader/IO)
    sH, eH = cfg.session.split("-")
    tag = f"{sH.replace(':','')}_{eH.replace(':','')}"

    # Cargar datos
    aliases = getattr(cfg, "aliases", None)
    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag, debug=False)

    # Asegurar ATR compat
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

    weights = (0.5, 0.3, 0.2)

    # ---------------- Calibración τ por ticker ----------------
    cal_start = cfg.calibration["start"]
    cal_end = cfg.calibration["end"]
    grid = cfg.calibration["tau_grid"]

    tau_by_ticker: dict[str, dict[str, float]] = {}
    scans_out = []

    print("🔧 Calibrando τ por ticker...")
    for t in cfg.tickers:
        # Fechas de calibración para este ticker (solo si hay datos diarios)
        dates_cal = pick_dates_for_ticker(d1_map, t, cal_start, cal_end)
        if not dates_cal:
            print(f"⚠️ {t}: sin fechas de calibración en [{cal_start} → {cal_end}] o sin datos 1d.")
            continue

        # Generar señales "crudas" (sin filtro τ) SOLO para este ticker
        try:
            sig_t = generate_daily_signals(
                {t: d1_map[t]}, rf, svm, lstm,
                0.0, 0.0, [t], dates_cal, weights
            )
        except Exception as e:
            print(f"⚠️ {t}: error generando señales para calibración: {e}")
            continue

        # Escaneo τ para BUY y SELL (usa ejecución real con 1h/1d)
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

        try:
            tau_buy, pnl_buy, scan_buy = scan_tau_pnl(sig_t, "BUY",  h1_map, d1_map, grid, exec_cfg)
            tau_sell, pnl_sell, scan_sell = scan_tau_pnl(sig_t, "SELL", h1_map, d1_map, grid, exec_cfg)
        except Exception as e:
            print(f"⚠️ {t}: error en scan_tau_pnl: {e}")
            continue

        tau_by_ticker[t] = {"BUY": float(tau_buy), "SELL": float(tau_sell)}
        # Guardar scans por ticker
        scan_buy.to_csv(reports_dir / f"tau_scan_{t.replace('.','_')}_BUY.csv", index=False)
        scan_sell.to_csv(reports_dir / f"tau_scan_{t.replace('.','_')}_SELL.csv", index=False)
        scans_out.append((t, tau_buy, tau_sell))
        print(f"  • {t}: τ*_BUY={tau_buy}  τ*_SELL={tau_sell}")

    # Persistir thresholds por ticker
    with open("models/thresholds_by_ticker.json", "w", encoding="utf-8") as f:
        json.dump(tau_by_ticker, f, indent=2, ensure_ascii=False)
    print("📝 τ* por ticker guardado en models/thresholds_by_ticker.json")

    # Defaults (por si algún ticker no calibró)
    tau_global_buy = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("BUY", 0.5))
    tau_global_sell = float(getattr(cfg, "calibration", {}).get("tau_star", {}).get("SELL", 0.5))

    # ---------------- Escenarios de ejecución ----------------
    scenarios: dict[str, dict] = {
        "baseline": dict(
            tp_atr_mult=cfg.exec.tp_atr_mult,
            sl_atr_mult=cfg.exec.sl_atr_mult,
            commission_pct=cfg.exec.commission_pct,
            slippage_pct=cfg.exec.slippage_pct,
            max_holding_days=cfg.exec.max_holding_days,
            trail_atr_mult=cfg.exec.trail_atr_mult,
            trail_activation_atr=cfg.exec.trail_activation_atr,
            break_even_atr=cfg.exec.break_even_atr,
        ),
        "trail_aggr": dict(
            tp_atr_mult=cfg.exec.tp_atr_mult,
            sl_atr_mult=cfg.exec.sl_atr_mult,
            commission_pct=cfg.exec.commission_pct,
            slippage_pct=cfg.exec.slippage_pct,
            max_holding_days=cfg.exec.max_holding_days,
            trail_atr_mult=0.8,
            trail_activation_atr=0.5,
            break_even_atr=0.7,
        ),
        "no_trail": dict(
            tp_atr_mult=cfg.exec.tp_atr_mult,
            sl_atr_mult=cfg.exec.sl_atr_mult,
            commission_pct=cfg.exec.commission_pct,
            slippage_pct=cfg.exec.slippage_pct,
            max_holding_days=cfg.exec.max_holding_days,
            trail_atr_mult=0.0,
            trail_activation_atr=cfg.exec.trail_activation_atr,
            break_even_atr=cfg.exec.break_even_atr,
        ),
        "longer_hold": dict(
            tp_atr_mult=cfg.exec.tp_atr_mult,
            sl_atr_mult=cfg.exec.sl_atr_mult,
            commission_pct=cfg.exec.commission_pct,
            slippage_pct=cfg.exec.slippage_pct,
            max_holding_days=5,
            trail_atr_mult=cfg.exec.trail_atr_mult,
            trail_activation_atr=cfg.exec.trail_activation_atr,
            break_even_atr=cfg.exec.break_even_atr,
        ),
        "tighter_sl": dict(
            tp_atr_mult=cfg.exec.tp_atr_mult,
            sl_atr_mult=0.8,  # SL más ceñido
            commission_pct=cfg.exec.commission_pct,
            slippage_pct=cfg.exec.slippage_pct,
            max_holding_days=cfg.exec.max_holding_days,
            trail_atr_mult=cfg.exec.trail_atr_mult,
            trail_activation_atr=cfg.exec.trail_activation_atr,
            break_even_atr=cfg.exec.break_even_atr,
        ),
        "wider_tp": dict(
            tp_atr_mult=1.8,  # TP más ambicioso
            sl_atr_mult=cfg.exec.sl_atr_mult,
            commission_pct=cfg.exec.commission_pct,
            slippage_pct=cfg.exec.slippage_pct,
            max_holding_days=cfg.exec.max_holding_days,
            trail_atr_mult=cfg.exec.trail_atr_mult,
            trail_activation_atr=cfg.exec.trail_activation_atr,
            break_even_atr=cfg.exec.break_even_atr,
        ),
    }

    # Fechas de evaluación (usa primer ticker disponible como ancla)
    eval_start = cfg.evaluation["start"]
    eval_end = cfg.evaluation["end"]
    # ancla: primer ticker con datos
    anchor = next((t for t in cfg.tickers if t in d1_map and not d1_map[t].empty), None)
    if anchor is None:
        raise RuntimeError("No hay datos diarios para evaluación.")
    dates_eval = [d for d in d1_map[anchor].index if (pd.Timestamp(eval_start) <= d < pd.Timestamp(eval_end))]
    if not dates_eval:
        raise RuntimeError(f"No hay fechas de evaluación entre {eval_start} y {eval_end}.")

    summary_rows = []

    print("\n🧪 Probando escenarios de ejecución...")
    for scen_name, exec_cfg in scenarios.items():
        # Generar señales con τ por ticker
        sig_list = []
        for t in cfg.tickers:
            if t not in d1_map or d1_map[t].empty:
                continue
            try:
                tau_t_buy = tau_by_ticker.get(t, {}).get("BUY", tau_global_buy)
                tau_t_sell = tau_by_ticker.get(t, {}).get("SELL", tau_global_sell)
                sig_t = generate_daily_signals(
                    {t: d1_map[t]}, rf, svm, lstm,
                    tau_t_buy, tau_t_sell, [t], dates_eval, weights
                )
                if sig_t is not None and not sig_t.empty:
                    sig_list.append(sig_t)
            except Exception as e:
                print(f"⚠️ {t}: error generando señales en escenario {scen_name}: {e}")
                continue

        sig_eval = pd.concat(sig_list, ignore_index=True) if sig_list else pd.DataFrame(columns=["ticker","date","side","prob"])

        # Backtest del escenario
        trades_df = run_backtest(sig_eval, h1_map, d1_map, exec_cfg)

        # Guardar trades del escenario
        trades_path = reports_dir / f"trades_{scen_name}.csv"
        trades_df.to_csv(trades_path, index=False)
        # KPIs
        met = kpis(trades_df)
        met["scenario"] = scen_name
        summary_rows.append(met)

        print(f"  • {scen_name}: {met}")

    # Resumen de escenarios
    summary_df = pd.DataFrame(summary_rows).sort_values("PnL_sum", ascending=False)
    summary_df.to_csv(reports_dir / "scenario_summary.csv", index=False)
    print("\n📊 Resumen escenarios (ordenado por PnL_sum):")
    print(summary_df)
    print(f"\n✅ Listo. Archivos en: {reports_dir}")
