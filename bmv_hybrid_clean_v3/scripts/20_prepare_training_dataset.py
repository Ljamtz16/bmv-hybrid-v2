# scripts/20_prepare_training_dataset.py
import argparse, os, pandas as pd, numpy as np
from pathlib import Path
import re

NUM_FEATS = ["tp", "sl"]
CAT_FEATS = ["ticker", "side", "reason"]

# === Ajustes de normalización / tolerancia ===
ROUND_DECIMALS = 3           # redondeo previo a merge
TP_TOL_ABS     = 0.06        # tolerancia absoluta si no empata exacto (p.ej. 6 centavos)
SL_TOL_ABS     = 0.06
TP_TOL_PCT     = 0.004       # tolerancia porcentual (0.4%) sobre entry_price
SL_TOL_PCT     = 0.004

def build_label_from_forecast_vs_real(df):
    s = df["outcome_real"].astype(str).str.upper().str.strip()
    y = s.map({"TP":1, "HIT_TP":1, "TP_FIRST":1, "SL":0, "HIT_SL":0, "SL_FIRST":0})
    if "pnl_sign_real" in df.columns:
        pnl_pos = (pd.to_numeric(df["pnl_sign_real"], errors="coerce") > 0).astype(int)
        mask_time = s.isin(["TIME","TIME_FALLBACK"])
        y = y.where(~mask_time, pnl_pos)
    return y.astype(int)

def _normalize_side(s):
    return s.astype(str).str.upper().str.strip().replace({"COMPRA":"BUY","VENTA":"SELL"})

def _round_price_cols(df, cols, nd=ROUND_DECIMALS):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(nd)
    return df

def _merge_exact(trades, real, key_cols):
    m = pd.merge(trades, real, on=key_cols, how="inner", suffixes=("_L","_R"))
    return m

def _merge_with_tolerance(trades, real):
    """
    Fuzzy merge usando tolerancia sobre TP/SL.
    Asume que ticker, side, entry_date empatan 1-a-1 por día (si hubiese >1, elegimos el más cercano).
    """
    # 1) primero unimos por ticker/side/entry_date para obtener posibles pares
    base_keys = ["ticker","side","entry_date"]
    L = trades.copy()
    R = real.copy()

    # si hay duplicados por base_keys, mantenemos el primero (o podrías resolver con combinatoria si realmente hay multi-trades por día)
    L = L.sort_values(base_keys).drop_duplicates(base_keys, keep="first")
    R = R.sort_values(base_keys).drop_duplicates(base_keys, keep="first")

    cand = pd.merge(L, R, on=base_keys, how="inner", suffixes=("_L","_R"))
    if cand.empty:
        return cand

    # 2) calcular diferencias
    for c in ("tp","sl","entry_price"):
        if f"{c}_L" in cand.columns:
            cand[f"{c}_L"] = pd.to_numeric(cand[f"{c}_L"], errors="coerce")
        if f"{c}_R" in cand.columns:
            cand[f"{c}_R"] = pd.to_numeric(cand[f"{c}_R"], errors="coerce")

    cand["tp_diff_abs"] = (cand["tp_L"] - cand["tp_R"]).abs()
    cand["sl_diff_abs"] = (cand["sl_L"] - cand["sl_R"]).abs()

    # tolerancia mixta: max(abs, pct * entry_price)
    tol_tp = np.maximum(TP_TOL_ABS, TP_TOL_PCT * cand["entry_price_L"].abs().fillna(0))
    tol_sl = np.maximum(SL_TOL_ABS, SL_TOL_PCT * cand["entry_price_L"].abs().fillna(0))

    keep = (cand["tp_diff_abs"] <= tol_tp) & (cand["sl_diff_abs"] <= tol_sl)
    cand = cand.loc[keep].copy()

    return cand

def load_month_rows(month: str):
    base = Path("reports/forecast") / month / "validation"
    trades_path = base / "validation_trades_auto.csv"
    join_path   = base / "validation_join_auto.csv"
    if trades_path.exists():
        trades = pd.read_csv(trades_path)
    elif join_path.exists():
        trades = pd.read_csv(join_path)
    else:
        print(f"⚠️ {month}: no encontré validation_trades_auto.csv ni validation_join_auto.csv, omito.")
        return None

    fvr = base / "forecast_vs_real.csv"
    if not fvr.exists():
        print(f"⚠️ {month}: no encontré forecast_vs_real.csv (corre primero el 13), omito.")
        return None
    real = pd.read_csv(fvr)

    # Normalizaciones básicas
    for df in (trades, real):
        # fechas
        for c in ["entry_date","exit_date","date","entry","exit"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        # side
        if "side" in df.columns:
            df["side"] = _normalize_side(df["side"])
        # precios numéricos
        for c in ("tp","sl","entry_price","exit_price_real"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    # Relleno de entry_price si faltara en L
    if "entry_price" in trades.columns and trades["entry_price"].isna().all():
        # intentar usar 'close' si existiera; si no, se queda NaN
        if "close" in trades.columns:
            trades["entry_price"] = pd.to_numeric(trades["close"], errors="coerce")

    # Redondeos previos (misma precisión en ambos lados)
    trades = _round_price_cols(trades, ["tp","sl","entry_price"], nd=ROUND_DECIMALS)
    real   = _round_price_cols(real,   ["tp","sl","entry_price"], nd=ROUND_DECIMALS)

    # 1) intentamos merge EXACTO por ticker,side,entry_date,tp,sl
    key_cols = ["ticker","side","entry_date","tp","sl"]
    if not all(c in trades.columns for c in key_cols) or not all(c in real.columns for c in key_cols):
        print(f"⚠️ {month}: falta alguna columna clave para merge exacto; intento fuzzy por fecha.")
        exact = pd.DataFrame()
    else:
        exact = _merge_exact(trades, real[key_cols + ["outcome_real","pnl_sign_real"]], key_cols)

    merged = exact

    # 2) si exacto quedó vacío, probamos fuzzy con tolerancia
    if merged.empty:
        fuzzy = _merge_with_tolerance(trades[["ticker","side","entry_date","tp","sl","entry_price"]],
                                      real[["ticker","side","entry_date","tp","sl","entry_price","outcome_real","pnl_sign_real"]])
        if not fuzzy.empty:
            merged = fuzzy
        else:
            # 3) último recurso: unir solo por ticker/side/entry_date (asumiendo 1 trade por día)
            base_keys = ["ticker","side","entry_date"]
            L = trades.sort_values(base_keys).drop_duplicates(base_keys, keep="first")
            R = real.sort_values(base_keys).drop_duplicates(base_keys, keep="first")
            merged = pd.merge(L, R[base_keys + ["outcome_real","pnl_sign_real"]], on=base_keys, how="inner", suffixes=("_L","_R"))

    if merged.empty:
        print(f"⚠️ {month}: merge vacío, omito.")
        return None

    # Generar etiqueta
    merged["outcome_real"] = merged["outcome_real"].astype(str)
    merged["y"] = build_label_from_forecast_vs_real(merged)

    # Estandarizar columnas de salida comunes
    # Mantendremos: y, entry_date, entry_price, tp, sl, ticker, side, reason (si existe)
    out = pd.DataFrame()
    out["y"] = merged["y"]
    out["entry_date"] = merged["entry_date"]
    # entry_price preferimos el del lado L si existe, si no el R
    if "entry_price_L" in merged.columns:
        out["entry_price"] = pd.to_numeric(merged["entry_price_L"], errors="coerce")
    elif "entry_price" in merged.columns:
        out["entry_price"] = pd.to_numeric(merged["entry_price"], errors="coerce")
    else:
        out["entry_price"] = np.nan

    # tp/sl del lado trades si existen, si no del lado real
    for c in ("tp","sl"):
        if f"{c}_L" in merged.columns:
            out[c] = pd.to_numeric(merged[f"{c}_L"], errors="coerce").round(ROUND_DECIMALS)
        elif c in merged.columns:
            out[c] = pd.to_numeric(merged[c], errors="coerce").round(ROUND_DECIMALS)
        else:
            out[c] = np.nan

    out["ticker"] = merged["ticker"]
    out["side"]   = merged["side"]
    if "reason" in merged.columns:
        out["reason"] = merged["reason"]
    elif "reason_pred" in merged.columns:
        out["reason"] = merged["reason_pred"]
    else:
        out["reason"] = ""

    return out

def add_numeric_features(df):
    # ATR% (si existe ATR_14 y close)
    if "ATR_14" in df.columns and "close" in df.columns:
        df["atr_pct"] = df["ATR_14"] / df["close"]
    # Rango intradía
    if "high" in df.columns and "low" in df.columns:
        df["range_intraday"] = df["high"] - df["low"]
    # Momentum D1 (5 días)
    if "close" in df.columns:
        df["momentum_d1"] = df["close"] - df["close"].shift(5)
    # Momentum H1 (si existe)
    if "close_h1" in df.columns:
        df["momentum_h1"] = df["close_h1"] - df["close_h1"].shift(5)
    return df

def add_classification_features(df):
    # ATR% (si existe ATR_14 y close)
    if "ATR_14" in df.columns and "close" in df.columns:
        df["atr_pct"] = df["ATR_14"] / df["close"]
    # Rango intradía
    if "high" in df.columns and "low" in df.columns:
        df["range_intraday"] = df["high"] - df["low"]
    # Gap
    if "open" in df.columns and "close" in df.columns:
        df["gap"] = df["open"] - df["close"].shift(1)
    # Momentum D1 (5 días)
    if "close" in df.columns:
        df["momentum_d1"] = df["close"] - df["close"].shift(5)
        df["trend_5d"] = np.sign(df["close"] - df["close"].shift(5))
    # Momentum H1 (si existe)
    if "close_h1" in df.columns:
        df["momentum_h1"] = df["close_h1"] - df["close_h1"].shift(5)
    return df

def normalize_months(months):
    return [re.sub(r'[^0-9\-]', '', m) for m in months]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", required=True, help="Meses históricos: YYYY-MM ...")
    ap.add_argument("--out", default="reports/forecast/training_dataset.csv")
    args = ap.parse_args()

    args.months = normalize_months(args.months)

    rows = []
    for m in args.months:
        r = load_month_rows(m)
        if r is not None:
            rows.append(r)

    if not rows:
        print("❌ No se pudo construir dataset. Revisa archivos de entrada.")
        return

    data = pd.concat(rows, ignore_index=True)

    # Mantener columnas esperadas por el resto del pipeline
    cols = ["y","entry_date","entry_price"] + NUM_FEATS + CAT_FEATS
    for c in cols:
        if c not in data.columns:
            data[c] = np.nan if c in (["entry_price"] + NUM_FEATS) else ""
    data = data[cols].copy()

    # Agregar features numéricas
    data = add_numeric_features(data)
    data = add_classification_features(data)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    data.to_csv(args.out, index=False)
    print(f"✅ Dataset guardado en {args.out} con {len(data)} filas. Columnas: {list(data.columns)}")

if __name__ == "__main__":
    main()
