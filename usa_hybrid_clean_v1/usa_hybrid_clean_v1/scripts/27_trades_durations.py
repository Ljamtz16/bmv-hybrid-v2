# =============================================
# 27_trades_durations.py
# =============================================
# Calcula duración y detalles de cada trade a partir de simulate_results.csv
# Uso:
#   python scripts/27_trades_durations.py --month 2025-10 \
#       --in-dir reports/forecast --out-dir reports/forecast
#
# Entrada esperada (columnas tolerantes):
#   - ticker, entry_date/entry_ts, exit_date/exit_ts (o horizon_days),
#   - entry_price, exit_price,
#   - pnl / net_pnl / rr,
#   - reason / tp_hit / sl_hit / horizon_hit,
#   - prob_win, y_hat, tp_pct(_suggested), sl_pct(_suggested), sector
#
# Salidas:
#   - trades_detailed.csv (por trade con duración y campos enriquecidos)
#   - trades_duration_summary.json (estadísticos de duración)

import argparse, os, json
import pandas as pd
import numpy as np


def _find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--in-dir", default="reports/forecast")
    ap.add_argument("--out-dir", default="reports/forecast")
    args = ap.parse_args()

    # Preferir archivo MERGED si existe
    base_dir = os.path.join(args.in_dir, args.month)
    merged_file = os.path.join(base_dir, "simulate_results_merged.csv")
    in_file = merged_file if os.path.exists(merged_file) else os.path.join(base_dir, "simulate_results.csv")
    if not os.path.exists(in_file):
        raise SystemExit(f"No existe: {in_file}")

    df = pd.read_csv(in_file)
    df.columns = [c.strip().lower() for c in df.columns]

    # Detectar columnas clave (tolerante a nombres distintos)
    col_entry_ts = _find_col(df, ["entry_ts","entry_time","open_ts","timestamp_entry","entry_date"])
    col_exit_ts  = _find_col(df, ["exit_ts","close_ts","timestamp_exit","exit_date"])
    col_entry_dt = _find_col(df, ["entry_date","date_entry","date"])
    col_exit_dt  = _find_col(df, ["exit_date","date_exit"])
    col_h        = _find_col(df, ["horizon_days","h","horizon"])
    col_pnl      = _find_col(df, ["pnl","net_pnl","net_pnl_usd"])
    col_rr       = _find_col(df, ["rr","ret","return","rr_trade"])
    col_reason   = _find_col(df, ["reason","close_reason","exit_reason"])
    col_tp_hit   = _find_col(df, ["tp_hit","take_profit_hit","tp"])
    col_sl_hit   = _find_col(df, ["sl_hit","stop_loss_hit","sl"])
    col_prob     = _find_col(df, ["prob_win","probability","pwin"])
    col_yhat     = _find_col(df, ["y_hat","yhat","pred_return"])
    col_tp_pct   = _find_col(df, ["tp_pct_suggested","tp_pct"])
    col_sl_pct   = _find_col(df, ["sl_pct_suggested","sl_pct"])
    col_sector   = _find_col(df, ["sector"])
    col_ticker   = _find_col(df, ["ticker","symbol"])

    # Parseo de fechas
    def to_datetime_safe(s):
        try:
            return pd.to_datetime(s, utc=True, errors="coerce")
        except Exception:
            return pd.to_datetime(s, errors="coerce")

    # Entry timestamp: preferir *_ts; si no, *_date
    if col_entry_ts and df[col_entry_ts].notna().any():
        df["entry_dt"] = to_datetime_safe(df[col_entry_ts])
    elif col_entry_dt:
        df["entry_dt"] = to_datetime_safe(df[col_entry_dt])
    else:
        raise SystemExit("No se encontró columna de fecha de entrada (entry_ts/entry_date).")

    # Exit timestamp: si no hay, estimar con horizonte (si existe)
    if col_exit_ts and df[col_exit_ts].notna().any():
        df["exit_dt"] = to_datetime_safe(df[col_exit_ts])
    elif col_exit_dt and df[col_exit_dt].notna().any():
        df["exit_dt"] = to_datetime_safe(df[col_exit_dt])
    else:
        # estimar con horizon_days (si existe)
        if not col_h:
            # sin horizon y sin exit -> no se puede calcular duración real
            df["exit_dt"] = pd.NaT
        else:
            # estimar: exit = entry + H días
            df["exit_dt"] = df["entry_dt"] + pd.to_timedelta(df[col_h].fillna(0), unit="D")

    # Duración
    df["duration_td"] = df["exit_dt"] - df["entry_dt"]
    # Métricas de duración en días/horas redondeadas
    df["duration_days"]  = df["duration_td"].dt.total_seconds() / 86400.0
    df["duration_hours"] = df["duration_td"].dt.total_seconds() / 3600.0

    # Deduplicar posibles duplicados exactos (misma operación repetida por capas)
    dedupe_keys = []
    if col_ticker:
        dedupe_keys.append(col_ticker)
    # Usar columnas estandarizadas calculadas
    dedupe_keys.append("entry_dt")
    if "exit_dt" in df.columns:
        dedupe_keys.append("exit_dt")
    # Incluir pnl o rr si existen para robustez
    if col_pnl:
        dedupe_keys.append(col_pnl)
    elif col_rr:
        dedupe_keys.append(col_rr)
    if dedupe_keys:
        before = len(df)
        df = df.drop_duplicates(subset=dedupe_keys, keep="first")
        after = len(df)
        if after < before:
            print(f"[trades] Deduplicados {before - after} registros (claves: {dedupe_keys})")

    # Motivo de cierre (prioridad: reason; si no, derivado de flags)
    if col_reason and df[col_reason].notna().any():
        df["close_reason"] = df[col_reason].astype(str)
    else:
        cond_tp = df[col_tp_hit]==1 if col_tp_hit in df.columns else False
        cond_sl = df[col_sl_hit]==1 if col_sl_hit in df.columns else False
        cond_h  = (df["duration_days"].round(6) >= df.get(col_h, pd.Series(np.nan)).fillna(np.nan)) if col_h else False
        df["close_reason"] = np.select(
            [cond_tp, cond_sl, cond_h],
            ["TP_HIT","SL_HIT","HORIZON_END"],
            default="UNKNOWN"
        )

    # Campos de salida estandarizados
    out_cols = []
    def add(cname, src):
        if src in df.columns:
            out_cols.append((cname, src))

    add("ticker", col_ticker or "ticker")
    add("sector", col_sector or "sector")
    add("entry_dt", "entry_dt")
    add("exit_dt",  "exit_dt")
    add("duration_days", "duration_days")
    add("duration_hours","duration_hours")
    add("horizon_days", col_h or "horizon_days")
    add("prob_win", col_prob or "prob_win")
    add("y_hat", col_yhat or "y_hat")
    add("tp_pct", col_tp_pct or "tp_pct_suggested")
    add("sl_pct", col_sl_pct or "sl_pct_suggested")
    # Sizing opcional si existe
    add("entry_price", "entry_price")
    add("exit_price", "exit_price")
    add("shares", "shares")
    add("cash_used", "cash_used")
    add("pnl_reconstructed", "pnl_reconstructed")
    add("pnl", col_pnl or "pnl")
    add("rr",  col_rr  or "rr")
    add("close_reason", "close_reason")

    out_df = pd.DataFrame({dst: df[src] for dst, src in out_cols})

    # Resumen estadístico de duración
    valid_dur = out_df["duration_days"].replace([np.inf,-np.inf], np.nan).dropna()
    summary = {
        "trades": int(len(out_df)),
        "duration_days_mean": float(valid_dur.mean()) if len(valid_dur) else None,
        "duration_days_median": float(valid_dur.median()) if len(valid_dur) else None,
        "duration_days_p25": float(valid_dur.quantile(0.25)) if len(valid_dur) else None,
        "duration_days_p75": float(valid_dur.quantile(0.75)) if len(valid_dur) else None,
        "duration_days_min": float(valid_dur.min()) if len(valid_dur) else None,
        "duration_days_max": float(valid_dur.max()) if len(valid_dur) else None
    }

    out_dir = os.path.join(args.out_dir, args.month)
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "trades_detailed.csv")
    out_json = os.path.join(out_dir, "trades_duration_summary.json")

    out_df.to_csv(out_csv, index=False)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[trades] Detalle -> {out_csv} (rows={len(out_df)})")
    print(f"[trades] Resumen duración -> {out_json}")
    print(f"[trades] Ejemplo primeras columnas: {list(out_df.columns)[:10]}")


if __name__ == "__main__":
    main()
