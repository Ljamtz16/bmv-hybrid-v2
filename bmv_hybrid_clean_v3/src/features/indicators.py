# src/features/indicators.py
from __future__ import annotations
import pandas as pd
import numpy as np

# -------------------- utilidades internas --------------------

def _true_range(df: pd.DataFrame) -> pd.Series:
    """
    True Range (TR) por Wilder:
      TR = max(
        High - Low,
        |High - Close_prev|,
        |Low  - Close_prev|
      )
    Requiere columnas: High, Low, Close
    """
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)

    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr

def _wilder_smoothing(series: pd.Series, n: int) -> pd.Series:
    """
    Suavizado de Wilder:
      ATR_t = (ATR_{t-1} * (n-1) + TR_t) / n
    Implementación equivalente con EMA(alpha = 1/n).
    """
    return series.ewm(alpha=1.0 / float(n), adjust=False).mean()

# -------------------- API pública --------------------

def ensure_atr_14(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """
    Asegura las columnas:
      - TR
      - ATR{n}   (p.ej. ATR14)
      - ATR_{n}  (p.ej. ATR_14)  <-- alias para compatibilidad con otros módulos

    - No pisa columnas existentes si ya están correctas.
    - Si solo existe una de las dos (ATR14 o ATR_14), crea la otra como alias.
    - Devuelve una COPIA del DataFrame con las columnas añadidas.
    """
    required = {"High", "Low", "Close"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas para ATR: {missing}")

    out = df.copy()

    # 1) TR
    if "TR" not in out.columns:
        out["TR"] = _true_range(out)

    # 2) Nombres objetivo
    atr_no_underscore = f"ATR{n}"     # ej. ATR14
    atr_with_underscore = f"ATR_{n}"  # ej. ATR_14

    # 3) Calcular ATR si falta en ambas variantes
    if atr_no_underscore not in out.columns and atr_with_underscore not in out.columns:
        out[atr_no_underscore] = _wilder_smoothing(out["TR"], n=n)

    # 4) Asegurar ambos alias existan y sean idénticos
    if atr_no_underscore in out.columns and atr_with_underscore not in out.columns:
        out[atr_with_underscore] = out[atr_no_underscore]
    if atr_with_underscore in out.columns and atr_no_underscore not in out.columns:
        out[atr_no_underscore] = out[atr_with_underscore]

    return out

# ----------------------------------------------------------------------
# Opcional: helpers genéricos si en el futuro quieres ATR con otro n
# ----------------------------------------------------------------------

def ensure_atr(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Versión genérica: asegura TR, ATR{n} y ATR_{n} para un n arbitrario.
    """
    return ensure_atr_14(df, n=n)

def ensure_rsi(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    import pandas_ta as ta
    df = df.copy()
    if f"RSI_{n}" not in df.columns:
        df[f"RSI_{n}"] = ta.rsi(df["close"], length=n)
    return df

def ensure_macd(df: pd.DataFrame) -> pd.DataFrame:
    import pandas_ta as ta
    df = df.copy()
    if "MACD" not in df.columns:
        macd = ta.macd(df["close"])
        df["MACD"] = macd["MACD_12_26_9"]
        df["MACD_signal"] = macd["MACDs_12_26_9"]
    return df

def ensure_ema(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    import pandas_ta as ta
    df = df.copy()
    if f"EMA_{n}" not in df.columns:
        df[f"EMA_{n}"] = ta.ema(df["close"], length=n)
    return df

def ensure_sma(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    import pandas_ta as ta
    df = df.copy()
    if f"SMA_{n}" not in df.columns:
        df[f"SMA_{n}"] = ta.sma(df["close"], length=n)
    return df
