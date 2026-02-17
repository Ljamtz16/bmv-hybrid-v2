import pandas as pd
from datetime import timedelta

# ---------------- utilidades ----------------

def _row_at_or_before(df: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    """
    Devuelve la última fila cuyo índice <= date.
    Lanza ValueError si no hay ninguna barra anterior.
    """
    date = pd.to_datetime(date)
    if date in df.index:
        return df.loc[date]
    pos = df.index.searchsorted(date, side="right") - 1
    if pos < 0:
        raise ValueError(f"No hay datos diarios anteriores a {date} en el DataFrame.")
    return df.iloc[pos]

def _get_atr_value(row: pd.Series) -> float:
    """Lee ATR con compatibilidad de nombres: ATR_14 o ATR14."""
    if "ATR_14" in row.index:
        return float(row["ATR_14"])
    if "ATR14" in row.index:
        return float(row["ATR14"])
    raise KeyError("No se encontró ni 'ATR_14' ni 'ATR14' en el DataFrame diario.")

# ---------------- lógica principal ----------------

def atr_targets_daily(df_d, date, side, tp_mult, sl_mult):
    """
    Usa la barra diaria más cercana ≤ date (as-of) para obtener Close y ATR.
    Evita KeyError cuando el índice no está a medianoche.
    """
    # no normalizamos a medianoche: usamos as-of directamente
    date = pd.to_datetime(date)

    row = _row_at_or_before(df_d, date)
    atr = _get_atr_value(row)
    close = float(row["Close"])

    if side == "BUY":
        tp = close + tp_mult * atr
        sl = close - sl_mult * atr
    else:
        tp = close - tp_mult * atr
        sl = close + sl_mult * atr

    return float(tp), float(sl), float(atr), float(close)

def finalize_trade(ticker, D, side, entry, exit_px, reason, prob):
    pnl = (exit_px - entry) if side == "BUY" else (entry - exit_px)
    return {
        "ticker": ticker,
        "date": str(pd.to_datetime(D).date()),
        "side": side,
        "entry": float(entry),
        "exit": float(exit_px),
        "pnl": float(pnl),
        "reason": reason,
        "prob": float(prob),
    }

def execute_hybrid_v2(
    h1_map, d1_map, ticker, date, side, prob,
    tp_mult=1.5, sl_mult=1.0,
    commission=0.001, slippage=0.0002,
    max_holding_days=3, trail_atr_mult=1.0, trail_activation_atr=0.5, break_even_atr=1.0
):
    df_h = h1_map[ticker]
    df_d = d1_map[ticker]
    D = pd.to_datetime(date).date()

    # niveles desde diario (as-of)
    tp, sl, atr_entry, close_entry = atr_targets_daily(df_d, D, side, tp_mult, sl_mult)

    open_found = False
    entry_px = None
    peak = None
    trough = None

    for day_offset in range(0, max_holding_days + 1):
        Dn = pd.to_datetime(D) + timedelta(days=day_offset)

        # seleccionar todas las barras 1h del día Dn
        try:
            day_df = df_h.loc[str(Dn.date())]
            # si el loc de un día devuelve Series (un solo bar), conviértelo a DF
            if isinstance(day_df, pd.Series):
                day_df = day_df.to_frame().T
        except KeyError:
            # no hay barras ese día
            continue

        if day_df.empty:
            continue

        O = day_df.iloc[0]["Open"]
        if not open_found:
            entry_px = O * (1 + slippage) if side == "BUY" else O * (1 - slippage)
            peak = entry_px if side == "BUY" else None
            trough = entry_px if side == "SELL" else None
            open_found = True

        for _, bar in day_df.iterrows():
            H = bar["High"]; L = bar["Low"]; O_bar = bar["Open"]

            # --- SL primero (incluye gaps) ---
            if side == "BUY":
                if L <= sl:
                    px = max(sl, O_bar) * (1 - commission)
                    return finalize_trade(ticker, D, side, entry_px, px, "SL", prob)
            else:
                if H >= sl:
                    px = min(sl, O_bar) * (1 + commission)
                    return finalize_trade(ticker, D, side, entry_px, px, "SL", prob)

            # --- TP ---
            if side == "BUY" and H >= tp:
                px = min(tp, O_bar) * (1 - commission)
                return finalize_trade(ticker, D, side, entry_px, px, "TP", prob)
            if side == "SELL" and L <= tp:
                px = max(tp, O_bar) * (1 + commission)
                return finalize_trade(ticker, D, side, entry_px, px, "TP", prob)

            # --- Trailing + break-even ---
            if trail_atr_mult > 0.0:
                move = (H - entry_px) if side == "BUY" else (entry_px - L)
                if move >= trail_activation_atr * atr_entry:
                    if move >= break_even_atr * atr_entry:
                        sl = max(sl, entry_px) if side == "BUY" else min(sl, entry_px)

                    if side == "BUY":
                        peak = max(peak, H) if peak is not None else H
                        trail = peak - trail_atr_mult * atr_entry
                        sl = max(sl, trail)
                        if L <= sl:
                            px = max(sl, O_bar) * (1 - commission)
                            return finalize_trade(ticker, D, side, entry_px, px, "TRAIL_SL", prob)
                    else:
                        trough = min(trough, L) if trough is not None else L
                        trail = trough + trail_atr_mult * atr_entry
                        sl = min(sl, trail)
                        if H >= sl:
                            px = min(sl, O_bar) * (1 + commission)
                            return finalize_trade(ticker, D, side, entry_px, px, "TRAIL_SL", prob)

        # último día: cerrar al close del último bar 1h disponible
        if day_offset == max_holding_days:
            close_px = day_df.iloc[-1]["Close"]
            px = close_px * (1 - commission) if side == "BUY" else close_px * (1 + commission)
            return finalize_trade(ticker, D, side, entry_px, px, "Close_LastDay", prob)

    # No hubo barras en toda la ventana
    return {
        "ticker": ticker,
        "date": str(D),
        "side": side,
        "entry": None,
        "exit": None,
        "pnl": 0.0,
        "reason": "NoBars",
        "prob": float(prob),
    }
        