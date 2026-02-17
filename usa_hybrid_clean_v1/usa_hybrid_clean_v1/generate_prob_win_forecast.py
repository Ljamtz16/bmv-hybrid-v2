#!/usr/bin/env python3
"""
generate_prob_win_forecast.py

Genera prob_win histórico a partir de intraday 15m (consolidated_15m.parquet).
Pipeline:
 1) Carga intraday y arma OHLCV diario por ticker.
 2) Calcula features diarios (retornos, ATR, posición en rango, gaps, vol).
 3) Etiqueta prob_win: con TP=1.6%, SL=1.0%, max_hold_days=2 (intraday forward).
    Label = 1 si se toca TP antes que SL en las siguientes barras; 0 en caso contrario.
 4) Entrena un modelo simple (Logistic Regression) si sklearn está disponible; si no, usa media móvil de la etiqueta.
 5) Exporta forecast parquet con columnas: date, ticker, prob_win, prob_win_cal (si modela), más features opcionales.

Uso:
  python generate_prob_win_forecast.py \
    --intraday C:/Users/.../consolidated_15m.parquet \
    --output data/daily/forecast_prob_win.parquet
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False

# Parámetros por defecto
TP_PCT = 0.016  # 1.6%
SL_PCT = 0.010  # 1.0%
MAX_HOLD_DAYS = 2
BARS_PER_DAY = 26  # 15m ~ 6.5h
LOOKAHEAD_BARS = MAX_HOLD_DAYS * BARS_PER_DAY

# Features a calcular
FEATURE_COLUMNS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_5d",
    "vol_20d",
    "atr_14d",
    "pos_in_range_20d",
    "gap_pct",
]

def load_intraday(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    # Determinar columna de fecha/hora
    if "datetime" in df.columns:
        dt_col = "datetime"
    elif "timestamp" in df.columns:
        dt_col = "timestamp"
    else:
        dt_col = df.columns[0]
    df["datetime"] = pd.to_datetime(df[dt_col])
    if df["datetime"].dt.tz is not None:
        df["datetime"] = df["datetime"].dt.tz_localize(None)
    return df

def build_daily_ohlcv(df_intraday: pd.DataFrame) -> pd.DataFrame:
    # Asegurar orden
    df_intraday = df_intraday.sort_values(["ticker", "datetime"])
    # Resample diario por ticker
    grouped = []
    for ticker, g in df_intraday.groupby("ticker"):
        g = g.set_index("datetime")
        ohlcv = g.resample("1D").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna(subset=["open", "high", "low", "close"])
        ohlcv["ticker"] = ticker
        grouped.append(ohlcv.reset_index().rename(columns={"datetime": "date"}))
    daily = pd.concat(grouped, ignore_index=True)
    daily = daily.sort_values(["ticker", "date"])
    return daily

def compute_features(daily: pd.DataFrame) -> pd.DataFrame:
    def _feat(group: pd.DataFrame) -> pd.DataFrame:
        g = group.copy()
        g = g.sort_values("date")
        g["ret_1d"] = g["close"].pct_change(1)
        g["ret_5d"] = g["close"].pct_change(5)
        g["ret_20d"] = g["close"].pct_change(20)
        g["vol_5d"] = g["close"].pct_change().rolling(5).std()
        g["vol_20d"] = g["close"].pct_change().rolling(20).std()
        # ATR 14d
        tr = pd.concat([
            (g["high"] - g["low"]),
            (g["high"] - g["close"].shift()).abs(),
            (g["low"] - g["close"].shift()).abs()
        ], axis=1).max(axis=1)
        g["atr_14d"] = tr.rolling(14).mean() / g["close"]  # normalizado
        # Posición en rango 20d
        roll_max = g["high"].rolling(20).max()
        roll_min = g["low"].rolling(20).min()
        g["pos_in_range_20d"] = (g["close"] - roll_min) / (roll_max - roll_min + 1e-6)
        # Gap pct
        g["gap_pct"] = (g["open"] - g["close"].shift()) / g["close"].shift()
        return g
    feats = daily.groupby("ticker", group_keys=False).apply(_feat)
    feats = feats.dropna(subset=FEATURE_COLUMNS, how="any")
    return feats

def label_prob_win(df_intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Etiqueta diaria usando intraday forward con TP/SL."""
    labels = []
    intraday = df_intraday.sort_values(["ticker", "datetime"])
    for ticker, g in intraday.groupby("ticker"):
        g = g.reset_index(drop=True)
        # Índices por día para acceso rápido
        g["date"] = g["datetime"].dt.date
        day_indices = g.groupby("date").indices
        # Map date -> last idx of day
        dates_sorted = sorted(day_indices.keys())
        price_array = g["close"].values
        for d in dates_sorted:
            idx_end = day_indices[d][-1]  # último índice del día d
            entry_price = price_array[idx_end]
            tp_price = entry_price * (1 + TP_PCT)
            sl_price = entry_price * (1 - SL_PCT)
            # Lookahead
            start = idx_end + 1
            end = min(idx_end + LOOKAHEAD_BARS, len(price_array) - 1)
            if start >= len(price_array):
                continue
            window = price_array[start:end+1]
            hit_tp = np.argmax(window >= tp_price) if np.any(window >= tp_price) else None
            hit_sl = np.argmax(window <= sl_price) if np.any(window <= sl_price) else None
            label = None
            if hit_tp is not None and hit_sl is not None:
                label = 1 if hit_tp < hit_sl else 0
            elif hit_tp is not None:
                label = 1
            elif hit_sl is not None:
                label = 0
            else:
                label = 0  # timeout se considera no-gana
            labels.append({"date": pd.to_datetime(d), "ticker": ticker, "label": label})
    df_labels = pd.DataFrame(labels)
    return df_labels

def train_model(df: pd.DataFrame):
    if not SKLEARN_AVAILABLE:
        return None
    X = df[FEATURE_COLUMNS].values
    y = df["label"].values
    # Eliminamos rows con NaN
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X = X[mask]
    y = y[mask]
    if len(y) < 100:
        return None
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=500))
    ])
    pipe.fit(X, y)
    return pipe

def main():
    parser = argparse.ArgumentParser(description="Generar prob_win histórico desde intraday 15m")
    parser.add_argument("--intraday", default="C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet")
    parser.add_argument("--output", default="data/daily/forecast_prob_win.parquet")
    args = parser.parse_args()

    print("[INFO] Cargando intraday...")
    df_intraday = load_intraday(args.intraday)
    print(f"  Rows: {len(df_intraday)} | Tickers: {df_intraday['ticker'].nunique()}")

    print("[INFO] Construyendo OHLCV diario...")
    daily = build_daily_ohlcv(df_intraday)
    print(f"  Rows diarios: {len(daily)}")

    print("[INFO] Calculando features...")
    feats = compute_features(daily)
    print(f"  Rows con features: {len(feats)}")

    print("[INFO] Generando labels prob_win (TP/SL forward intraday)...")
    labels = label_prob_win(df_intraday, feats)
    print(f"  Labels: {len(labels)}")

    # Merge features + labels
    df_ml = feats.merge(labels, on=["date", "ticker"], how="inner")
    print(f"  Dataset ML: {len(df_ml)} rows")

    model = train_model(df_ml)
    if model is None:
        print("[WARN] sklearn no disponible o dataset pequeño: se usará prob_win rolling 60d")

    # Generar forecast (solo usando información hasta T-1)
    forecasts = []
    for ticker, g in df_ml.groupby("ticker"):
        g = g.sort_values("date")
        if model is None:
            g["prob_win"] = g["label"].rolling(60, min_periods=10).mean().shift(1)
        else:
            X = g[FEATURE_COLUMNS]
            probs = model.predict_proba(X)[:, 1]
            # Desplazamos una fila para evitar look-ahead
            g["prob_win"] = pd.Series(probs, index=g.index).shift(1)
        # Calibración trivial: clamp
        g["prob_win_cal"] = g["prob_win"].clip(0.01, 0.99)
        forecasts.append(g[["date", "ticker", "prob_win_cal", "prob_win"] + FEATURE_COLUMNS])
    df_forecast = pd.concat(forecasts, ignore_index=True).dropna(subset=["prob_win_cal"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_forecast.to_parquet(output_path, index=False)
    print(f"[OK] Forecast guardado en {output_path} | Rows: {len(df_forecast)}")

if __name__ == "__main__":
    main()
