# scripts/_reuse_26_policy.py
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict

def normalize_side(side_val):
    """Convierte cualquier indicador de lado a 'BUY' o 'SELL' (o NaN si no aplica)."""
    if pd.isna(side_val):
        return np.nan
    s = str(side_val).strip().upper()
    if s in {"BUY", "LONG", "1", "BULL"}:
        return "BUY"
    elif s in {"SELL", "SHORT", "-1", "BEAR"}:
        return "SELL"
    elif s in {"0", "FLAT", "NONE", "NAN"}:
        return np.nan
    return s


def apply_policy(df: pd.DataFrame, pol: Dict) -> pd.DataFrame:
    """
    Aplica una política de TP/SL/H sobre un DataFrame de validación.

    Requiere columnas:
      - entry_price (float)
      - side (opcional; si falta se asume BUY)
      - price_d1..price_dH (preferible) o ret_Hd (fallback)
      - y_pred (opcional; si existe se puede filtrar con min_abs_y)

    Parámetros en pol:
      tp_pct, sl_pct, horizon_days, per_trade_cash, commission_side, min_abs_y (opcional), long_only (opcional)

    Devuelve:
      DF con columnas extra: tp_price, sl_price, exit_price_sim, exit_reason, shares, gross_pnl, net_pnl
    """
    out = df.copy()

    # --- Filtro por magnitud de predicción (si aplica) ---
    if "y_pred" in out.columns:
        min_abs_y = float(pol.get("min_abs_y", 0.0))
        out = out.loc[out["y_pred"].abs() >= min_abs_y].copy()

    # --- Normalizar lado (BUY/SELL) ---
    if "side" not in out.columns:
        out["side"] = "BUY"
    else:
        out["side"] = out["side"].apply(normalize_side)
        if out["side"].isna().all():  # si quedó todo NaN, asumimos BUY
            out["side"] = "BUY"

    # Forzar long-only si se pide
    if bool(pol.get("long_only", False)):
        out["side"] = "BUY"

    tp_pct = float(pol["tp_pct"])
    sl_pct = float(pol["sl_pct"])
    ep = out["entry_price"].astype(float)

    is_buy  = out["side"].eq("BUY")
    is_sell = out["side"].eq("SELL")

    # --- Niveles TP/SL ---
    out["tp_price"] = np.where(
        is_buy, ep * (1.0 + tp_pct),
        np.where(is_sell, ep * (1.0 - tp_pct), np.nan)
    )
    out["sl_price"] = np.where(
        is_buy, ep * (1.0 - sl_pct),
        np.where(is_sell, ep * (1.0 + sl_pct), np.nan)
    )

    # --- Salida por horizonte ---
    H = int(pol["horizon_days"])
    price_cols = [c for c in out.columns if c.startswith("price_d")]

    if not price_cols:
        # Fallback por retorno a H días
        ret_col = f"ret_{H}d"
        if ret_col in out.columns:
            out["exit_price_sim"] = ep * (1.0 + pd.to_numeric(out[ret_col], errors="coerce").fillna(0.0))
            out["exit_reason"] = "horizon"
        else:
            out["exit_price_sim"] = ep
            out["exit_reason"] = "none"
    else:
        # Buscar primer toque TP/SL dentro de 1..H; si no, se va por horizonte
        price_cols = sorted(price_cols, key=lambda s: int(s.replace("price_d", "")))[:H]
        hits, reasons = [], []

        for _, row in out.iterrows():
            tp = float(row["tp_price"])
            sl = float(row["sl_price"])
            e = float(row["entry_price"])
            s = row["side"]
            chosen_price, reason = None, None

            for c in price_cols:
                p = row.get(c)
                if pd.isna(p):
                    continue
                p = float(p)

                if s == "BUY":
                    if p >= tp:
                        chosen_price, reason = tp, "tp"; break
                    if p <= sl:
                        chosen_price, reason = sl, "sl"; break
                elif s == "SELL":
                    if p <= tp:
                        chosen_price, reason = tp, "tp"; break
                    if p >= sl:
                        chosen_price, reason = sl, "sl"; break

            if chosen_price is None:
                last_col = price_cols[-1]
                last_px = row.get(last_col)
                chosen_price = float(last_px) if pd.notna(last_px) else e
                reason = "horizon"

            hits.append(chosen_price)
            reasons.append(reason)

        out["exit_price_sim"] = hits
        out["exit_reason"] = reasons

    # --- Sizing y PnL ---
    per_trade_cash = float(pol.get("per_trade_cash", 1000.0))
    comm = float(pol.get("commission_side", 5.0))

    out["shares"] = np.floor(per_trade_cash / ep).astype(int).clip(lower=0)
    exit_px = out["exit_price_sim"].astype(float)

    # BUY: (exit-entry)*shares | SELL: (entry-exit)*shares
    gross_buy  = (exit_px - ep) * out["shares"]
    gross_sell = (ep - exit_px) * out["shares"]
    out["gross_pnl"] = np.where(is_buy, gross_buy,
                         np.where(is_sell, gross_sell, 0.0))

    # Comisión ida+vuelta plana por trade
    out["net_pnl"] = out["gross_pnl"] - (2.0 * comm)

    return out


def compute_kpis(out: pd.DataFrame, month: str, pol: Dict) -> Dict:
    """
    Calcula KPIs agregados sobre el DataFrame resultante de apply_policy.
    Devuelve dict con tasas TP/SL/Horizon, PnL y metadatos de la política.
    """
    tp_rate = float((out["exit_reason"] == "tp").mean()) if "exit_reason" in out.columns else None
    sl_rate = float((out["exit_reason"] == "sl").mean()) if "exit_reason" in out.columns else None
    hz_rate = float((out["exit_reason"] == "horizon").mean()) if "exit_reason" in out.columns else None

    return {
        "month": month,
        "trades": int(out.shape[0]),
        "tp_rate": tp_rate,
        "sl_rate": sl_rate,
        "horizon_rate": hz_rate,
        "gross_pnl_sum": float(out["gross_pnl"].sum()) if "gross_pnl" in out.columns else None,
        "net_pnl_sum": float(out["net_pnl"].sum()) if "net_pnl" in out.columns else None,
        # Meta de política (útil para trazabilidad)
        "tp_pct": float(pol.get("tp_pct", np.nan)),
        "sl_pct": float(pol.get("sl_pct", np.nan)),
        "horizon_days": int(pol.get("horizon_days", 0)),
        "min_abs_y": float(pol.get("min_abs_y", 0.0)),
        "per_trade_cash": float(pol.get("per_trade_cash", 1000.0)),
        "commission_side": float(pol.get("commission_side", 5.0)),
        "long_only": bool(pol.get("long_only", False)),
    }
