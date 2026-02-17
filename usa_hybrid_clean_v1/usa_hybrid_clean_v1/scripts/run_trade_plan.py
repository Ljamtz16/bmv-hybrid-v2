#!/usr/bin/env python3
"""
Script: run_trade_plan.py
Wrapper oficial para generar trade plan.
- Maneja CSV y Parquet automáticamente
- Valida schema
- Genera audit log
- Ejecuta 33_make_trade_plan.py
- POST-PROCESS: ETTH (Expected Time To Hit) usando ATR14 real
"""

import argparse
import pandas as pd
import numpy as np
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import math

# ========== FUNCIONES ETTH (POST-PROCESO) ==========

def _true_range(df: pd.DataFrame) -> pd.Series:
    """True Range por fila (requiere high, low, prev_close)."""
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

def compute_atr14_pct(
    prices: pd.DataFrame,
    asof_date: str,
    window: int = 14,
) -> pd.DataFrame:
    """
    Calcula ATR(window) y ATR% por ticker usando historial <= asof_date.
    prices: columnas esperadas: date/timestamp, ticker, open, high, low, close, volume.
    Retorna DF: ticker, atr14, atr14_pct, last_close_used, n_obs
    """
    # Normaliza columna fecha
    if "date" in prices.columns:
        dt_col = "date"
    elif "timestamp" in prices.columns:
        dt_col = "timestamp"
    else:
        raise ValueError("prices debe tener columna 'date' o 'timestamp'")

    p = prices.copy()
    p[dt_col] = pd.to_datetime(p[dt_col]).dt.date
    asof = pd.to_datetime(asof_date).date()
    p = p[p[dt_col] <= asof]

    # Asegura tipos numéricos
    for c in ["open", "high", "low", "close"]:
        p[c] = pd.to_numeric(p[c], errors="coerce")

    # Orden y cálculo por ticker
    p = p.sort_values(["ticker", dt_col])

    out_rows = []
    for tkr, g in p.groupby("ticker", sort=False):
        g = g.dropna(subset=["high", "low", "close"])
        n_obs = len(g)
        if n_obs < max(3, window):  # sin historial suficiente
            out_rows.append((tkr, np.nan, np.nan, g["close"].iloc[-1] if n_obs else np.nan, n_obs))
            continue

        tr = _true_range(g)
        # ATR simple (SMA del TR)
        atr = tr.rolling(window=window, min_periods=window).mean().iloc[-1]
        last_close = g["close"].iloc[-1]
        atr_pct = atr / last_close if (pd.notna(atr) and pd.notna(last_close) and last_close != 0) else np.nan
        out_rows.append((tkr, atr, atr_pct, last_close, n_obs))

    return pd.DataFrame(out_rows, columns=["ticker", "atr14", "atr14_pct", "last_close_used", "n_obs"])

def add_etth_days_to_trade_plan(
    trade_plan: pd.DataFrame,
    atr_table: pd.DataFrame,
    eps: float = 1e-6,
    clamp_min: float = 0.5,
    clamp_max: float = 10.0,
) -> pd.DataFrame:
    """
    ETTH proxy: distancia a TP (%) / ATR% (ATR14_pct).
    - BUY: dist_tp_pct = (tp_price-entry)/entry
    - SELL (si existiera): dist_tp_pct = (entry-tp_price)/entry
    """
    tp = trade_plan.copy()
    tp["entry"] = pd.to_numeric(tp["entry"], errors="coerce")
    tp["tp_price"] = pd.to_numeric(tp["tp_price"], errors="coerce")

    merged = tp.merge(atr_table[["ticker", "atr14_pct", "n_obs"]], on="ticker", how="left")

    def dist_tp_pct(row):
        if pd.isna(row["entry"]) or row["entry"] == 0 or pd.isna(row["tp_price"]):
            return np.nan
        side = str(row.get("side", "BUY")).upper()
        if side == "SELL":
            return (row["entry"] - row["tp_price"]) / row["entry"]
        return (row["tp_price"] - row["entry"]) / row["entry"]

    merged["dist_tp_pct"] = merged.apply(dist_tp_pct, axis=1)
    merged["atr14_pct_safe"] = merged["atr14_pct"].clip(lower=eps)

    merged["etth_days_raw"] = merged["dist_tp_pct"] / merged["atr14_pct_safe"]
    merged["etth_days"] = merged["etth_days_raw"].clip(lower=clamp_min, upper=clamp_max)

    # Quality flags
    merged["etth_degraded"] = False
    degraded_mask = merged["atr14_pct"].isna() | merged["dist_tp_pct"].isna()
    merged.loc[degraded_mask, "etth_degraded"] = True
    merged.loc[degraded_mask, "etth_days"] = np.nan  # si está degradado, no inventamos

    return merged

# ========== HELPER: EXPOSURE CAP (GREEDY) ==========
def apply_exposure_cap(df: pd.DataFrame, exposure_cap: float):
    """
    Greedy cap in existing row order (already strength order from 33).
    Keeps trades until cap reached; sets qty=0 for remaining trades.
    Returns: (df_out, cap_info dict)
    """
    if exposure_cap is None:
        return df, {"cap_applied": False}

    required = ["exposure", "qty", "entry"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"trade_plan output missing required column: {col}")

    exposure_before = float(df["exposure"].sum())
    cap = float(exposure_cap)

    # Nothing to do
    if exposure_before <= cap:
        return df, {
            "cap_applied": False,
            "exposure_before": exposure_before,
            "exposure_after": exposure_before,
            "exposure_cap": cap,
            "removed_trades": 0,
            "qty_modified_rows": 0,
        }

    running = 0.0
    removed = 0
    qty_changed = 0

    out = df.copy()

    for i in range(len(out)):
        row_qty = float(out.loc[i, "qty"]) if not pd.isna(out.loc[i, "qty"]) else 0.0
        row_exp = float(out.loc[i, "entry"]) * float(row_qty)

        if row_qty <= 0 or row_exp <= 0:
            out.loc[i, "qty"] = 0
            out.loc[i, "exposure"] = 0.0
            continue

        if running + row_exp <= cap:
            running += row_exp
        else:
            out.loc[i, "qty"] = 0
            out.loc[i, "exposure"] = 0.0
            removed += 1
            qty_changed += 1

    exposure_after = float(out["exposure"].sum())

    if exposure_after > cap + 1e-6:
        raise RuntimeError(f"Exposure cap failed: after={exposure_after} cap={cap}")

    return out, {
        "cap_applied": True,
        "exposure_before": exposure_before,
        "exposure_after": exposure_after,
        "exposure_cap": cap,
        "removed_trades": removed,
        "qty_modified_rows": qty_changed,
    }

# ========== EXECUTION MODES (POST-PROCESO) ==========

def _execution_defaults(mode: str) -> dict:
    mode = (mode or "balanced").lower()
    return {
        "mode": mode,
        "etth_max": {"intraday": 2.0, "fast": 3.5, "balanced": 6.0, "conservative": 10.0}.get(mode, 6.0),
        "score_formula": {
            "intraday": "strength / (0.5 + etth_days)",
            "fast": "strength / etth_days",
            "balanced": "0.7*strength + 0.3*(1/etth_days_norm)",
            "conservative": "strength",
        }.get(mode, "0.7*strength + 0.3*(1/etth_days_norm)"),
    }


def apply_execution_mode(
    df: pd.DataFrame,
    mode: str = "balanced",
    exposure_cap: float = None,
    etth_max_override: float = None,
    min_strength: float = 0.0,
    min_prob_win: float = 0.0,
):
    """
    Aplica modo de ejecución como post-proceso (sin reordenar CSV final).
    1) Calcula exec_score
    2) Filtra elegibles (ETTH, min_strength, min_prob_win)
    3) Aplica cap greedy PRIORITIZANDO exec_score (no el orden CSV)
    4) Devuelve DF en orden original (strength del core)
    Retorna: df_out, exec_info(dict)
    """

    if df.empty:
        return df, {}

    df = df.copy()
    df["_orig_idx"] = np.arange(len(df))

    defaults = _execution_defaults(mode)
    mode_logic = defaults["mode"]

    # Si no hay ETTH, forzamos balanced con warning
    exec_info = {
        "requested_mode": mode_logic,
        "mode_used": mode_logic,
        "etth_available": "etth_days" in df.columns and not df["etth_days"].isna().all(),
        "warnings": [],
    }
    if not exec_info["etth_available"]:
        exec_info["warnings"].append("ETTH no disponible; usando modo balanced")
        mode_logic = "balanced"
        defaults = _execution_defaults(mode_logic)

    etth_max = etth_max_override if etth_max_override is not None else defaults["etth_max"]
    score_formula = defaults["score_formula"]

    reason_counts = {"etth": 0, "strength": 0, "prob": 0, "cap": 0, "missing_etth": 0}
    drop_reasons_by_ticker = []

    def compute_score(row):
        etth = row.get("etth_days", np.nan)
        etth_norm = np.nanmax([etth, 0.5]) if not pd.isna(etth) else np.nan
        if mode_logic == "intraday":
            return row["strength"] / (0.5 + etth_norm) if not pd.isna(etth_norm) and etth_norm != 0 else np.nan
        if mode_logic == "fast":
            return row["strength"] / etth_norm if not pd.isna(etth_norm) and etth_norm != 0 else np.nan
        if mode_logic == "balanced":
            return 0.7 * row["strength"] + 0.3 * (1.0 / etth_norm) if not pd.isna(etth_norm) else 0.7 * row["strength"]
        return row["strength"]

    eligible_flags = []
    scores = []
    drop_reasons = []

    for _, row in df.iterrows():
        reasons = []
        etth = row.get("etth_days", np.nan)
        if mode_logic != "conservative" or etth_max_override is not None:
            if pd.isna(etth):
                reasons.append("missing_etth")
            elif etth_max is not None and etth > etth_max:
                reasons.append("etth")
        if row.get("strength", 0) < min_strength:
            reasons.append("strength")
        if row.get("prob_win", 0) < min_prob_win:
            reasons.append("prob")

        if reasons:
            for r in reasons:
                reason_counts[r] = reason_counts.get(r, 0) + 1
            eligible_flags.append(False)
            scores.append(np.nan)
            drop_reasons.append(reasons[0])
        else:
            eligible_flags.append(True)
            score_val = compute_score(row)
            scores.append(score_val)
            drop_reasons.append(None)

    df["eligible"] = eligible_flags
    df["exec_score"] = scores
    df["drop_reason"] = drop_reasons

    # Filtrar elegibles y ordenar por prioridad
    eligible_df = df[df["eligible"]].copy()
    sort_cols = ["exec_score", "strength", "prob_win"]
    sort_orders = [False, False, False]
    if "etth_days" in eligible_df.columns:
        sort_cols.append("etth_days")
        sort_orders.append(True)  # menor ETTH primero en empate
    eligible_df = eligible_df.sort_values(sort_cols, ascending=sort_orders, na_position="last")

    exposure_before = float(df.get("exposure", pd.Series(dtype=float)).sum()) if "exposure" in df.columns else 0.0
    exposure_after = exposure_before
    kept = set()

    running = 0.0
    for _, row in eligible_df.iterrows():
        idx = int(row["_orig_idx"])
        qty = float(row.get("qty", 0) or 0)
        exp = float(row.get("exposure", 0) or 0)
        if qty <= 0 or exp <= 0:
            df.loc[df["_orig_idx"] == idx, "qty"] = 0
            df.loc[df["_orig_idx"] == idx, "exposure"] = 0.0
            continue
        if exposure_cap is None or running + exp <= float(exposure_cap):
            running += exp
            kept.add(idx)
        else:
            df.loc[df["_orig_idx"] == idx, ["qty", "exposure", "eligible"]] = [0, 0.0, False]
            df.loc[df["_orig_idx"] == idx, "drop_reason"] = "cap"
            reason_counts["cap"] += 1
            drop_reasons_by_ticker.append({"ticker": row.get("ticker"), "reason": "cap"})

    # Los ineligibles se quedan con qty=0
    for _, row in df[~df["eligible"]].iterrows():
        idx = int(row["_orig_idx"])
        if idx not in kept:
            df.loc[df["_orig_idx"] == idx, ["qty", "exposure"]] = [0, 0.0]
            drop_reasons_by_ticker.append({"ticker": row.get("ticker"), "reason": row.get("drop_reason")})

    # Restaura orden original
    df = df.sort_values("_orig_idx").drop(columns=["_orig_idx"])
    exposure_after = float(df.get("exposure", pd.Series(dtype=float)).sum()) if "exposure" in df.columns else 0.0

    exec_info.update({
        "etth_max_used": float(etth_max) if etth_max is not None else None,
        "score_formula": score_formula,
        "exposure_cap": float(exposure_cap) if exposure_cap is not None else None,
        "exposure_before": exposure_before,
        "exposure_after": exposure_after,
        "eligible_trades": int(df["eligible"].sum()),
        "kept_trades": int(len(kept)),
        "dropped_trades": int(len(df) - len(kept)),
        "reason_counts": reason_counts,
        "dropped": drop_reasons_by_ticker,
    })

    return df, exec_info

# ========== FUNCIONES WRAPPER ==========

def load_forecast_auto(path: str) -> tuple:
    """Carga forecast desde CSV o Parquet, retorna (df, formato_original)"""
    path = Path(path)
    
    if path.suffix.lower() == '.parquet':
        df = pd.read_parquet(path)
        return df, "parquet"
    elif path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
        return df, "csv"
    else:
        raise ValueError(f"Formato no soportado: {path.suffix}. Use .csv o .parquet")

def validate_forecast_schema(df: pd.DataFrame) -> dict:
    """Valida que el forecast tenga columnas críticas"""
    required_cols = ["prob_win"]
    optional_cols = ["prob_raw", "prob_temp", "ticker", "date", "side"]
    
    issues = []
    missing_required = [c for c in required_cols if c not in df.columns]
    if missing_required:
        issues.append(f"Columnas requeridas FALTANTES: {missing_required}")
    
    missing_optional = [c for c in optional_cols if c not in df.columns]
    if missing_optional:
        print(f"[WARN] Columnas opcionales FALTANTES: {missing_optional}")
    
    return {"valid": len(issues) == 0, "issues": issues, "missing_optional": missing_optional}

def prepare_forecast_csv(df: pd.DataFrame, output_path: str):
    """
    Prepara forecast para consumo por 33_make_trade_plan.py
    - Asegurar que tiene prob_win
    - Imputar 'side' si falta (BUY si prob_win > 0.5, SELL si <= 0.5)
    - NO agregar y_hat fake
    """
    # Validar
    validation = validate_forecast_schema(df)
    if not validation["valid"]:
        raise ValueError(f"Schema inválido:\n" + "\n".join(validation["issues"]))
    
    # Imputar 'side' si falta
    if "side" not in df.columns:
        print("[INFO] Imputando columna 'side' basada en prob_win > 0.5")
        df = df.copy()
        df["side"] = df["prob_win"].apply(lambda x: "BUY" if x > 0.5 else "SELL")
    
    # Limpiar: remover y_hat si existe (no lo queremos)
    if "y_hat" in df.columns:
        print("[INFO] Removiendo columna y_hat (será derivada correctamente)")
        df = df.drop(columns=["y_hat"])
    
    # Guardar como CSV
    df.to_csv(output_path, index=False)
    print(f"[OK] Forecast preparado: {output_path}")
    return df, validation

def main():
    ap = argparse.ArgumentParser(
        description="Wrapper para generar trade plan desde forecast (CSV o Parquet)"
    )
    ap.add_argument("--forecast", required=True, help="Ruta a forecast.csv o forecast.parquet")
    ap.add_argument("--prices", required=True, help="Ruta a prices_file (CSV o Parquet)")
    ap.add_argument("--out", required=True, help="Archivo de salida trade_plan.csv")
    ap.add_argument("--month", required=True, help="Mes para filtro (YYYY-MM)")
    ap.add_argument("--capital", type=float, default=100000, help="Capital total")
    ap.add_argument("--exposure-cap", type=float, default=None, help="Tope de exposición total (si se especifica, ajusta qty para no excederlo)")
    ap.add_argument("--execution-mode", choices=["intraday", "fast", "balanced", "conservative"], default="balanced", help="Modo de ejecución (post-proceso)")
    ap.add_argument("--etth-max", type=float, default=None, help="Límite máximo de ETTH (override manual)")
    ap.add_argument("--min-strength", type=float, default=0.0, help="Filtro mínimo de strength")
    ap.add_argument("--min-prob-win", type=float, default=0.0, help="Filtro mínimo de prob_win")
    ap.add_argument("--max-open", type=int, default=15, help="Max posiciones abiertas")
    ap.add_argument("--tp-pct", type=float, default=0.10, help="Take profit %")
    ap.add_argument("--sl-pct", type=float, default=0.02, help="Stop loss %")
    ap.add_argument("--asof-date", default=None, help="YYYY-MM-DD para filtro")
    ap.add_argument("--audit-file", default=None, help="JSON audit log (default: trade_plan_audit.json)")
    ap.add_argument("--dry-run", action="store_true", help="Validar sin ejecutar")
    
    args = ap.parse_args()
    
    # Paths internos
    forecast_csv_temp = "data/daily/forecast_temp_for_33.csv"
    prices_csv_temp = "data/daily/prices_temp_for_33.csv"
    audit_file = args.audit_file or "val/trade_plan_run_audit.json"
    
    try:
        print(f"[{'DRY-RUN' if args.dry_run else 'EXEC'}] Generando trade plan...")
        print(f"  Forecast: {args.forecast}")
        print(f"  Prices: {args.prices}")
        print(f"  Output: {args.out}")
        
        # === PASO 1: Cargar forecast ===
        print("\n[1/4] Cargando forecast...")
        f_df, f_fmt = load_forecast_auto(args.forecast)
        print(f"  Formato original: {f_fmt}, shape: {f_df.shape}")
        
        # === PASO 2: Cargar prices ===
        print("\n[2/4] Cargando prices...")
        p_df, p_fmt = load_forecast_auto(args.prices)  # Reutilizamos para ambos
        print(f"  Formato original: {p_fmt}, shape: {p_df.shape}")
        
        # === PASO 3: Preparar CSVs ===
        print("\n[3/4] Preparando CSVs para 33_make_trade_plan.py...")
        f_df, validation = prepare_forecast_csv(f_df, forecast_csv_temp)
        p_df.to_csv(prices_csv_temp, index=False)
        print(f"  OK: {forecast_csv_temp}, {prices_csv_temp}")
        
        if args.dry_run:
            print("\n[DRY-RUN] Validación completada sin ejecutar 33_make_trade_plan.py")
            sys.exit(0)
        
        # === PASO 4: Ejecutar 33_make_trade_plan.py ===
        print("\n[4/4] Ejecutando 33_make_trade_plan.py...")
        import subprocess
        cmd = [
            "python", "scripts/33_make_trade_plan.py",
            "--month", args.month,
            "--forecast_file", forecast_csv_temp,
            "--prices_file", prices_csv_temp,
            "--out", args.out,
            "--capital", str(args.capital),
            "--max-open", str(args.max_open),
            "--tp-pct", str(args.tp_pct),
            "--sl-pct", str(args.sl_pct),
        ]
        if args.asof_date:
            cmd.extend(["--asof-date", args.asof_date])
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0 and "Trade plan ->" not in result.stdout:
            print(f"[ERROR] 33_make_trade_plan.py falló:")
            print(result.stdout)
            print(result.stderr)
            sys.exit(1)
        
        print(result.stdout)
        
        # === POST-PROCESS: ETTH (sin tocar 33) ===
        etth_stats = {}
        cap_info = {}
        exec_info = {}
        try:
            tp_base = pd.read_csv(args.out)
            if not args.asof_date:
                print("\n[WARN] Sin --asof-date, ETTH post-proceso omitido")
                tp_etth = tp_base.copy()
                atr_tbl = pd.DataFrame()
            else:
                print("\n[POST-PROCESS] Calculando ETTH (ATR14 real)...")
                # Calcular ATR14 table desde historial real
                atr_tbl = compute_atr14_pct(p_df, asof_date=args.asof_date, window=14)
                # Agregar ETTH al trade plan
                tp_etth = add_etth_days_to_trade_plan(tp_base, atr_tbl)

            # Aplicar modos de ejecución + cap (greedy por prioridad, sin reordenar CSV final)
            try:
                df_exec, exec_info = apply_execution_mode(
                    tp_etth,
                    mode=args.execution_mode,
                    exposure_cap=args.exposure_cap,
                    etth_max_override=args.etth_max,
                    min_strength=args.min_strength,
                    min_prob_win=args.min_prob_win,
                )
                df_exec.to_csv(args.out, index=False)
                cap_info = {
                    "cap_applied": exec_info.get("exposure_cap") is not None and exec_info.get("exposure_after", 0) < exec_info.get("exposure_before", 0),
                    "exposure_before": exec_info.get("exposure_before"),
                    "exposure_after": exec_info.get("exposure_after"),
                    "exposure_cap": exec_info.get("exposure_cap"),
                    "removed_trades": exec_info.get("reason_counts", {}).get("cap", 0),
                }
                print("\n[POST-PROCESS] Modo de ejecución aplicado:")
                print(f"  Mode: {exec_info.get('mode_used')} (requested: {exec_info.get('requested_mode')})")
                print(f"  etth_max: {exec_info.get('etth_max_used')} | min_strength: {args.min_strength} | min_prob_win: {args.min_prob_win}")
                print(f"  exposure_cap: {exec_info.get('exposure_cap')}")
                print(f"  elegibles: {exec_info.get('eligible_trades')} | kept: {exec_info.get('kept_trades')} | dropped: {exec_info.get('dropped_trades')}")
                if exec_info.get("warnings"):
                    for w in exec_info["warnings"]:
                        print(f"  [WARN] {w}")
                if cap_info.get("cap_applied"):
                    print(f"  [ADJUST] Exposure cap: ${cap_info['exposure_before']:.2f} -> ${cap_info['exposure_after']:.2f} (cap=${cap_info['exposure_cap']:.2f}, dropped_cap={cap_info['removed_trades']})")
            except Exception as e:
                print(f"[WARN] Error aplicando execution-mode/cap: {type(e).__name__}: {e}")
                tp_etth.to_csv(args.out, index=False)

            # Stats para auditoría (solo si ETTH calculado)
            if args.asof_date:
                etth_valid = tp_etth["etth_days"].dropna()
                etth_stats = {
                    "etth_method": "atr14_proxy",
                    "etth_window": 14,
                    "etth_clamp_min": 0.5,
                    "etth_clamp_max": 10.0,
                    "etth_n": int(tp_etth.shape[0]),
                    "etth_nan_pct": float(tp_etth["etth_days"].isna().mean() * 100.0),
                    "etth_unique": int(tp_etth["etth_days"].nunique(dropna=True)),
                    "etth_mean": float(etth_valid.mean()) if len(etth_valid) else None,
                    "etth_min": float(etth_valid.min()) if len(etth_valid) else None,
                    "etth_max": float(etth_valid.max()) if len(etth_valid) else None,
                    "etth_degraded_count": int(tp_etth["etth_degraded"].sum()),
                    "atr14_pct_mean": float(atr_tbl["atr14_pct"].dropna().mean()) if not atr_tbl.empty and atr_tbl["atr14_pct"].notna().any() else None,
                    "atr14_pct_nan_pct": float(atr_tbl["atr14_pct"].isna().mean() * 100.0) if not atr_tbl.empty else None,
                }
                
                # Regla de seguridad: si etth no varía o está mayormente NaN, marcar degradado global
                if etth_stats["etth_unique"] <= 1 or (etth_stats["etth_nan_pct"] is not None and etth_stats["etth_nan_pct"] > 50.0):
                    etth_stats["etth_global_warning"] = "ETTH degraded or non-informative (unique<=1 or NaN%>50)."
                    print(f"[WARN] {etth_stats['etth_global_warning']}")
                else:
                    print(f"[OK] ETTH: mean={etth_stats['etth_mean']:.2f}d, unique={etth_stats['etth_unique']}, NaN%={etth_stats['etth_nan_pct']:.1f}%")
            
        except Exception as e:
            # No rompemos el pipeline por ETTH (post-proceso opcional)
            etth_stats["etth_error"] = f"{type(e).__name__}: {e}"
            print(f"[WARN] ETTH post-proceso falló (no crítico): {etth_stats['etth_error']}")
        
        # === Audit Log ===
        import sklearn, joblib, xgboost, catboost, numpy
        
        # Detectar si 'side' fue imputada (basada en validation)
        side_imputed = "side" in validation.get("missing_optional", [])
        
        audit = {
            "timestamp": datetime.now().isoformat(),
            "status": "success",
            "forecast_original_fmt": f_fmt,
            "forecast_rows": int(f_df.shape[0]),
            "prices_rows": int(p_df.shape[0]),
            "output_file": args.out,
            "asof_date": args.asof_date,
            "capital": args.capital,
            "max_open": args.max_open,
            "tp_pct": args.tp_pct,
            "sl_pct": args.sl_pct,
            "forecast_issues": {
                "missing_optional_cols": validation.get("missing_optional", []),
                "side_imputed": side_imputed,
                "side_imputation_rule": "BUY if prob_win > 0.5 else SELL" if side_imputed else None,
            },
            "versions": {
                "scikit-learn": sklearn.__version__,
                "joblib": joblib.__version__,
                "numpy": numpy.__version__,
                "pandas": pd.__version__,
                "xgboost": xgboost.__version__,
                "catboost": catboost.__version__,
            }
        }

        if exec_info:
            audit["execution_mode"] = {
                "requested": exec_info.get("requested_mode"),
                "used": exec_info.get("mode_used"),
                "etth_max": exec_info.get("etth_max_used"),
                "score_formula": exec_info.get("score_formula"),
                "min_strength": args.min_strength,
                "min_prob_win": args.min_prob_win,
                "eligible_trades": exec_info.get("eligible_trades"),
                "kept_trades": exec_info.get("kept_trades"),
                "dropped_trades": exec_info.get("dropped_trades"),
                "reason_counts": exec_info.get("reason_counts"),
                "dropped": exec_info.get("dropped"),
                "exposure_before": exec_info.get("exposure_before"),
                "exposure_after": exec_info.get("exposure_after"),
                "exposure_cap": exec_info.get("exposure_cap"),
                "warnings": exec_info.get("warnings"),
            }
        
        # Añadir ETTH stats al audit
        if etth_stats:
            audit.update(etth_stats)
        # Añadir exposure cap info explícita
        if args.exposure_cap is not None:
            audit["exposure_cap"] = {
                "enabled": True,
                **({
                    "applied": bool(cap_info.get("cap_applied")),
                    "cap": float(cap_info.get("exposure_cap", 0) or 0),
                    "exposure_before": float(cap_info.get("exposure_before", 0) or 0),
                    "exposure_after": float(cap_info.get("exposure_after", 0) or 0),
                    "removed_trades": int(cap_info.get("removed_trades", 0) or 0),
                } if cap_info else {})
            }
        else:
            audit["exposure_cap"] = {"enabled": False}
        
        # Verificar output
        if os.path.exists(args.out):
            output_df = pd.read_csv(args.out)
            audit["output_rows"] = int(output_df.shape[0])
            audit["output_cols"] = int(output_df.shape[1])
            audit["prob_win_mean"] = float(output_df["prob_win"].mean())
            
            # Calcular exposure total
            exposure_total = float(output_df['exposure'].sum())
            audit["exposure_total"] = exposure_total
            
            # Mostrar resumen con ETTH
            print(f"\n[OK] Trade plan generado: {args.out} ({output_df.shape[0]} trades)")
            print(f"\n=== RESUMEN DIARIO ===")
            print(f"Trades:           {output_df.shape[0]}")
            print(f"BUY/SELL:         {(output_df['side'] == 'BUY').sum()} BUY, {(output_df['side'] == 'SELL').sum()} SELL")
            print(f"Prob Win (mean):  {output_df['prob_win'].mean():.2%}")
            print(f"Exposure (total): ${exposure_total:.2f}")
            
            # ETTH si existe
            if "etth_days" in output_df.columns:
                etth_mean = output_df["etth_days"].mean()
                etth_min = output_df["etth_days"].min()
                etth_max = output_df["etth_days"].max()
                etth_unique = output_df["etth_days"].nunique(dropna=True)
                etth_nan_pct = output_df["etth_days"].isna().mean() * 100
                
                audit["etth_days_mean"] = float(etth_mean)
                audit["etth_days_min"] = float(etth_min)
                audit["etth_days_max"] = float(etth_max)
                
                print(f"ETTH (mean):      {etth_mean:.2f} dias")
                print(f"ETTH (range):     {etth_min:.2f} - {etth_max:.2f} dias")
                
                # Warning si ETTH poco confiable
                if etth_unique <= 1:
                    print(f"WARN ETTH: Sin variabilidad (unique={etth_unique}), no usar para decisiones")
                elif etth_nan_pct > 20:
                    print(f"WARN ETTH: Alto NaN% ({etth_nan_pct:.1f}%), usar con precaución")
                
                # NOTA: CSV guardado en orden ORIGINAL (por strength del core)
                # Orden sugerido según execution-mode (exec_score desc, elegibles primero)
                print(f"\n=== ORDEN SUGERIDO DE EJECUCION ({args.execution_mode}) ===")
                print(f"NOTA: CSV mantiene orden original por strength")
                ordered = output_df.copy()
                if "exec_score" in ordered.columns:
                    ordered = ordered.sort_values(["eligible", "exec_score"], ascending=[False, False], na_position="last")
                for idx, (_, row) in enumerate(ordered.iterrows(), 1):
                    etth_val = row['etth_days'] if pd.notna(row['etth_days']) else 'N/A'
                    etth_str = f"{etth_val:.2f}d" if etth_val != 'N/A' else 'N/A'
                    flag = "DROP" if row.get("qty", 0) == 0 else "KEEP"
                    reason = row.get("drop_reason") if flag == "DROP" else ""
                    print(f"  {idx}. {row['ticker']:6s} | {row['side']:4s} | ${row['exposure']:7.2f} | "
                          f"prob={row['prob_win']:.1%} | etth={etth_str} | score={row.get('exec_score', float('nan')):.3f} | {flag} {reason}")
            print(f"=====================\n")
        
        # Guardar audit
        Path(audit_file).parent.mkdir(parents=True, exist_ok=True)
        with open(audit_file, "w") as f:
            json.dump(audit, f, indent=2)
        print(f"[OK] Audit log: {audit_file}")
        
        # Limpiar temporales
        for tmp in [forecast_csv_temp, prices_csv_temp]:
            if os.path.exists(tmp):
                os.remove(tmp)
                
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
