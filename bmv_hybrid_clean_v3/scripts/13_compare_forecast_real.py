# scripts/13_compare_forecast_real.py
from __future__ import annotations

import argparse
from pathlib import Path
import json
import pandas as pd

# ------------------------------------------------------------
# Helpers de lectura
# ------------------------------------------------------------

def read_hourly_csv(path: Path) -> pd.DataFrame:
    """
    Lee un CSV 1h y devuelve DF con índice datetime y columnas: Open, High, Low, Close.
    Soporta nombres comunes de columnas.
    """
    df = pd.read_csv(path)
    # Detectar columna datetime
    dt_col = None
    for c in df.columns:
        lc = c.lower()
        if lc in ("datetime", "timestamp", "date", "time"):
            dt_col = c
            break
    if dt_col is None:
        dt_col = df.columns[0]
    df[dt_col] = pd.to_datetime(df[dt_col])
    df = df.sort_values(dt_col).set_index(dt_col)

    # Normalizar OHLC
    rename_map = {}
    cols_l = {c.lower(): c for c in df.columns}
    for want in ("open", "high", "low", "close"):
        if want in cols_l:
            rename_map[cols_l[want]] = want.capitalize()
    df = df.rename(columns=rename_map)

    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns:
            raise ValueError(f"{path.name}: falta columna {col} (tras normalizar). Columnas={list(df.columns)}")

    return df[["Open", "High", "Low", "Close"]]


def load_forecast_trades(val_dir: Path) -> pd.DataFrame:
    """
    Busca y lee validation_trades_auto.csv o validation_join_auto.csv en val_dir.
    Normaliza columnas mínimas y soporta alias:
      - entry_date: entry_datetime, entry_ts, entry
      - exit_date:  exit_datetime, exit_ts, exit
      - tp/sl: tp, tp_price, ..., (si no existen se dejan NaN y se usa validación fallback)
    """
    join_path = val_dir / "validation_join_auto.csv"
    trades_path = val_dir / "validation_trades_auto.csv"
    if join_path.exists():
        df = pd.read_csv(join_path)
    elif trades_path.exists():
        df = pd.read_csv(trades_path)
    else:
        raise FileNotFoundError(
            f"No encontré ni {join_path.name} ni {trades_path.name} en {val_dir}. "
            f"Corre 10_validate_month_forecast.py primero."
        )

    df.columns = [c.strip() for c in df.columns]

    # renombres básicos
    time_renames = {
        "entry_datetime": "entry_date",
        "entry_ts": "entry_date",
        "entry": "entry_date",      # <-- importante para tu CSV
        "exit_datetime": "exit_date",
        "exit_ts": "exit_date",
        "exit": "exit_date",        # <-- importante para tu CSV
    }
    for k, v in time_renames.items():
        if k in df.columns and v not in df.columns:
            df = df.rename(columns={k: v})

    # columnas obligatorias base
    for col in ["ticker", "side"]:
        if col not in df.columns:
            raise ValueError(f"Falta columna requerida en forecast trades: {col}")

    # entry_date: usar 'entry_date' o 'date' si no existe
    if "entry_date" not in df.columns:
        if "date" in df.columns:
            df["entry_date"] = pd.to_datetime(df["date"], errors="coerce")
        else:
            raise ValueError("Falta 'entry_date' y tampoco existe 'date' para derivarlo.")
    df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")

    # exit_date opcional
    df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce") if "exit_date" in df.columns else pd.NaT

    # aliases TP/SL
    tp_aliases = ["tp", "tp_price", "tp_level", "take_profit", "take_profit_price", "takeprofit", "target_price"]
    sl_aliases = ["sl", "sl_price", "sl_level", "stop_loss", "stoploss", "stop_price"]

    def first_present(cols):
        for c in cols:
            if c in df.columns:
                return c
        return None

    tp_col = first_present(tp_aliases)
    sl_col = first_present(sl_aliases)

    df["tp"] = pd.to_numeric(df[tp_col], errors="coerce") if tp_col else pd.NA
    df["sl"] = pd.to_numeric(df[sl_col], errors="coerce") if sl_col else pd.NA

    if "reason" not in df.columns:
        df["reason"] = None
    if "pnl" not in df.columns:
        df["pnl"] = None

    # Deja pasar columnas opcionales por si existen (probabilidades / score)
    # No renombramos aquí; más adelante las consultamos por varios alias.
    df["ticker"] = df["ticker"].astype(str)
    df["side"] = df["side"].astype(str).str.upper()
    return df


# ------------------------------------------------------------
# Lógica de comparación barra-a-barra
# ------------------------------------------------------------

def simulate_tp_sl_on_1h(
    bars: pd.DataFrame,
    side: str,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp | None,
    tp: float,
    sl: float,
    tie_mode: str = "worst",
) -> dict:
    """
    Igual que antes: recorre barras [entry_ts, exit_ts) y determina TP/SL primero.
    """
    sub = bars.loc[bars.index >= entry_ts]
    if exit_ts is not None:
        sub = sub.loc[sub.index < exit_ts]
    if sub.empty:
        return dict(outcome_real="NO_DATA", exit_price=None, entry_price=None, pnl_sign_real=0, bars_used=0)

    entry_price = float(sub.iloc[0]["Open"])
    bars_used = 0
    side = side.upper()

    for _, row in sub.iterrows():
        bars_used += 1
        hi = float(row["High"])
        lo = float(row["Low"])

        if side == "BUY":
            tp_hit = (hi >= tp)
            sl_hit = (lo <= sl)
        else:
            tp_hit = (lo <= tp)
            sl_hit = (hi >= sl)

        if tp_hit and sl_hit:
            if tie_mode == "best":
                return dict(outcome_real="TP", exit_price=tp, entry_price=entry_price, pnl_sign_real=+1, bars_used=bars_used)
            else:
                return dict(outcome_real="SL", exit_price=sl, entry_price=entry_price, pnl_sign_real=-1, bars_used=bars_used)

        if tp_hit:
            return dict(outcome_real="TP", exit_price=tp, entry_price=entry_price, pnl_sign_real=+1, bars_used=bars_used)
        if sl_hit:
            return dict(outcome_real="SL", exit_price=sl, entry_price=entry_price, pnl_sign_real=-1, bars_used=bars_used)

    close_price = float(sub.iloc[-1]["Close"])
    delta = close_price - entry_price
    pnl_sign = 0
    if side == "BUY":
        pnl_sign = 1 if delta > 0 else (-1 if delta < 0 else 0)
    else:
        pnl_sign = 1 if delta < 0 else (-1 if delta > 0 else 0)

    return dict(outcome_real="TIME", exit_price=close_price, entry_price=entry_price, pnl_sign_real=pnl_sign, bars_used=bars_used)


def simulate_fallback_sign_on_1h(
    bars: pd.DataFrame,
    side: str,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp | None,
) -> dict:
    """
    Fallback cuando NO hay TP/SL:
      - Toma Open de la primera barra >= entry_ts
      - Toma Close de la última barra < exit_ts (o última disponible si exit_ts es NaT)
      - Devuelve outcome 'TIME_FALLBACK' y el signo de ganancia/perdida por lado.
    """
    sub = bars.loc[bars.index >= entry_ts]
    if exit_ts is not None:
        sub = sub.loc[sub.index < exit_ts]
    if sub.empty:
        return dict(outcome_real="NO_DATA", exit_price=None, entry_price=None, pnl_sign_real=None, bars_used=0)

    entry_price = float(sub.iloc[0]["Open"])
    exit_price = float(sub.iloc[-1]["Close"])
    side = side.upper()

    delta = exit_price - entry_price
    if side == "BUY":
        pnl_sign = 1 if delta > 0 else (-1 if delta < 0 else 0)
    else:
        pnl_sign = 1 if delta < 0 else (-1 if delta > 0 else 0)

    return dict(
        outcome_real="TIME_FALLBACK",
        exit_price=exit_price,
        entry_price=entry_price,
        pnl_sign_real=pnl_sign,
        bars_used=len(sub),
    )


def reason_to_pred_outcome(reason: str | None) -> str | None:
    if reason is None:
        return None
    r = str(reason).upper()
    if r == "TP":
        return "TP"
    if r in ("SL", "TRAIL_SL"):
        return "SL"
    if r in ("CLOSE_LASTDAY", "NOBARS", "TIME", "EXIT_TIME"):
        return "TIME"
    return None


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def run(month: str,
        hist_dir: str = "data/raw/1h",
        tie_mode: str = "worst",
        out_dir: str | None = None) -> None:

    base = Path("reports/forecast") / month
    val_dir = base / "validation"
    if out_dir is None:
        out_dir = val_dir
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    trades = load_forecast_trades(val_dir)

    # Cargar históricos por ticker bajo demanda
    hist_dir = Path(hist_dir)
    cache_bars: dict[str, pd.DataFrame] = {}

    results = []
    for _, row in trades.iterrows():
        ticker = str(row["ticker"])
        side = str(row["side"]).upper()
        entry_ts = pd.to_datetime(row["entry_date"])
        exit_ts = pd.to_datetime(row["exit_date"]) if ("exit_date" in row and pd.notna(row["exit_date"])) else None
        tp = float(row["tp"]) if ("tp" in row and pd.notna(row["tp"])) else None
        sl = float(row["sl"]) if ("sl" in row and pd.notna(row["sl"])) else None
        reason_pred = reason_to_pred_outcome(row.get("reason", None))
        pnl_pred = row.get("pnl", None)

        # === NUEVO: derivar y_score si existen probabilidades/score en el input ===
        # Soporta varios alias comunes: prob_long/prob_short, proba_long/proba_short,
        # prob_buy/prob_sell, y un único score/prob/confidence en [0,1].
        def get_first(series_like, aliases):
            for al in aliases:
                if al in series_like:
                    return series_like.get(al)
            return None

        # Nota: row.get retorna un valor; verificamos NaN con pd.notna luego.
        prob_long = get_first(row, [
            "prob_long", "proba_long", "prob_buy", "p_long", "proba_buy"
        ])
        prob_short = get_first(row, [
            "prob_short", "proba_short", "prob_sell", "p_short", "proba_sell"
        ])
        # Un único score/probabilidad (0..1 idealmente)
        score_single = get_first(row, [
            "y_score", "score", "prob", "proba", "proba_win", "confidence", "conf", "pred_prob"
        ])

        y_score = None
        try:
            if pd.notna(prob_long) or pd.notna(prob_short):
                # Si hay probas por lado, elige la del lado tomado
                if side in ("BUY", "LONG"):
                    y_score = float(prob_long)
                else:
                    y_score = float(prob_short)
            elif pd.notna(score_single):
                # Usa el score único (clipeado a [0,1] si aplica)
                y_score = float(score_single)
                if y_score < 0.0: y_score = 0.0
                if y_score > 1.0: y_score = 1.0
        except Exception:
            y_score = None  # si algo falla, lo dejamos vacío

        # DF 1h
        if ticker not in cache_bars:
            f1 = hist_dir / f"{ticker}_1h.csv"
            f2 = Path(f"{ticker}_1h.csv")
            if f1.exists():
                bars = read_hourly_csv(f1)
            elif f2.exists():
                bars = read_hourly_csv(f2)
            else:
                results.append({
                    "ticker": ticker, "side": side,
                    "entry_date": entry_ts, "exit_date": exit_ts,
                    "tp": tp, "sl": sl,
                    "reason_pred": reason_pred, "pnl_pred": pnl_pred,
                    "outcome_real": "NO_HIST",
                    "entry_price": None,
                    "exit_price_real": None,
                    "pnl_sign_real": None,
                    "pnl_real_pct": None,   # NUEVO: en ausencia de precios
                    "y_score": y_score,     # NUEVO: aunque no haya hist
                    "match_reason": False,
                    "bars_used": 0
                })
                continue
            cache_bars[ticker] = bars
        else:
            bars = cache_bars[ticker]

        if tp is not None and sl is not None:
            sim = simulate_tp_sl_on_1h(bars, side, entry_ts, exit_ts, tp, sl, tie_mode=tie_mode)
        else:
            sim = simulate_fallback_sign_on_1h(bars, side, entry_ts, exit_ts)

        match_reason = (reason_pred is not None and reason_pred == sim["outcome_real"])

        # === NUEVO: calcular pnl_real_pct con base en precios simulados y lado ===
        entry_price = sim["entry_price"]
        exit_price = sim["exit_price"]
        if entry_price is None or exit_price is None:
            pnl_real_pct = None
        else:
            try:
                if side in ("BUY", "LONG"):
                    pnl_real_pct = (exit_price - entry_price) / entry_price
                else:  # SELL / SHORT
                    pnl_real_pct = (entry_price - exit_price) / entry_price
            except Exception:
                pnl_real_pct = None

        results.append({
            "ticker": ticker, "side": side,
            "entry_date": entry_ts, "exit_date": exit_ts,
            "tp": tp, "sl": sl,
            "reason_pred": reason_pred,
            "pnl_pred": pnl_pred,
            "outcome_real": sim["outcome_real"],
            "entry_price": entry_price,
            "exit_price_real": exit_price,
            "pnl_sign_real": sim["pnl_sign_real"],
            "pnl_real_pct": pnl_real_pct,   # ← NUEVO
            "y_score": y_score,             # ← NUEVO
            "match_reason": bool(match_reason),
            "bars_used": sim["bars_used"],
        })

    out_csv = out_dir / "forecast_vs_real.csv"
    out_json = out_dir / "forecast_vs_real_metrics.json"
    df = pd.DataFrame(results)
    df.to_csv(out_csv, index=False, encoding="utf-8")

    # Métricas
    total = len(df)
    no_hist = int((df["outcome_real"] == "NO_HIST").sum()) if total else 0
    no_data = int((df["outcome_real"] == "NO_DATA").sum()) if total else 0
    # validaciones
    tp_sl_mask = df["outcome_real"].isin(["TP", "SL", "TIME"])
    fallback_mask = (df["outcome_real"] == "TIME_FALLBACK")
    valid_any_mask = tp_sl_mask | fallback_mask
    dfv = df.loc[valid_any_mask].copy()

    match_rate = float(dfv["match_reason"].mean() * 100.0) if not dfv.empty else 0.0

    # función para signo predicho
    def sign_from_pred_row(r) -> float | None:
        try:
            v = float(r.get("pnl_pred"))
            if pd.notna(v):
                if v > 0: return 1
                if v < 0: return -1
                return 0
        except Exception:
            pass
        rp = r.get("reason_pred")
        if rp == "TP": return 1
        if rp == "SL": return -1
        if rp == "TIME": return None
        return None

    pred_signs = dfv.apply(sign_from_pred_row, axis=1)
    valid_pred_mask = pred_signs.notna()
    winrate_pred = float((pred_signs[valid_pred_mask] > 0).mean() * 100.0) if valid_pred_mask.any() else None

    if "pnl_sign_real" in dfv.columns and dfv["pnl_sign_real"].notna().any():
        winrate_real = float((dfv["pnl_sign_real"] > 0).mean() * 100.0)
    else:
        winrate_real = None

    both_mask = valid_pred_mask & dfv["pnl_sign_real"].notna()
    sign_corr = float((pred_signs[both_mask] == dfv.loc[both_mask, "pnl_sign_real"]).mean() * 100.0) if both_mask.any() else None

    metrics = {
        "month": month,
        "total_trades": total,
        "validated_trades": int(dfv.shape[0]),
        "validated_trades_tp_sl": int(tp_sl_mask.sum()),
        "validated_trades_fallback": int(fallback_mask.sum()),
        "no_hist_files": no_hist,
        "no_data_window": no_data,
        "match_reason_%": round(match_rate, 2),
        "winrate_pred_%": None if winrate_pred is None else round(winrate_pred, 2),
        "winrate_real_%": None if winrate_real is None else round(winrate_real, 2),
        "sign_accuracy_%": None if sign_corr is None else round(sign_corr, 2),
        "tie_mode": tie_mode,
        "output_csv": str(out_csv)
    }

    with out_json.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(f"✅ Comparación lista.\nArchivo: {out_csv}")
    print("Métricas:", metrics)


def parse_args():
    p = argparse.ArgumentParser(description="Compara pronóstico (validation_trades_auto.csv) contra OHLC 1h real.")
    p.add_argument("--month", required=True, help="Mes a validar (YYYY-MM), ej: 2025-05")
    p.add_argument("--hist_dir", default="data/raw/1h", help="Directorio con CSVs de 1h (por ticker)")
    p.add_argument("--tie_mode", default="worst", choices=["worst", "best"], help="Resolución cuando TP y SL se tocan en la misma vela")
    p.add_argument("--out_dir", default=None, help="Directorio de salida (por defecto usa reports/forecast/<month>/validation)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(month=args.month, hist_dir=args.hist_dir, tie_mode=args.tie_mode, out_dir=args.out_dir)
