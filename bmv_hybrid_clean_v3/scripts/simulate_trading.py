#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulate_trading.py (robusto)

Simula ejecución de señales a un horizonte fijo (H días de trading) usando
Close_fwd_H{H}. Soporta múltiples formatos de 'signal':
  - numérico: 1, 0, -1 (int/str)
  - texto: 'BUY','LONG','SELL','SHORT','HOLD','FLAT' (case-insensitive)

Entrada:
  --month           AAAA-MM (para rutas de salida)
  --signals-csv     CSV con señales (p.ej. forecast_..._with_gate.csv)
  --capital-initial Capital inicial
  --fixed-cash      Efectivo por trade
  --tp-pct          Take Profit (ej. 0.08 = 8%)
  --sl-pct          Stop Loss  (ej. 0.02 = 2%)
  --horizon-days    H (3/5, etc.) usará Close_fwd_H{H} si existe
  --out-suffix      Sufijo para archivos de salida (evita sobreescritura)

Salidas:
  reports/forecast/<MES>/trades_<MES>[__SUF].csv
  reports/forecast/<MES>/simulation_summary_<MES>[__SUF].json
"""

import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

_TEXT2SIGNAL = {
    "BUY": 1, "LONG": 1, "B": 1, "L": 1, "GO LONG": 1,
    "SELL": -1, "SHORT": -1, "S": -1, "SH": -1, "GO SHORT": -1,
    "HOLD": 0, "FLAT": 0, "NONE": 0, "NO TRADE": 0
}

def parse_signal(val, fallback=None):
    """Normaliza 'signal' a {-1,0,1} desde numérico o texto; usa fallback si hay NaN."""
    if pd.isna(val) or val == "":
        val = fallback
    if pd.isna(val) or val == "":
        return 0
    # numérico directo
    try:
        f = float(val)
        if f > 0: return 1
        if f < 0: return -1
        return 0
    except Exception:
        pass
    # texto
    s = str(val).strip().upper()
    if s in _TEXT2SIGNAL: return _TEXT2SIGNAL[s]
    if s in {"+1", "1"}: return 1
    if s == "-1": return -1
    if s == "0": return 0
    return 0

def pick_entry_price(row):
    if "entry_price" in row and pd.notna(row["entry_price"]):
        return float(row["entry_price"])
    if "Close_t" in row and pd.notna(row["Close_t"]):
        return float(row["Close_t"])
    return np.nan

def cap_with_tp_sl(ret, side, tp, sl):
    """
    Cap aproximado al horizonte:
      side_ret = side * ret
      side_ret ∈ [-sl, +tp]
      retorno nominal = side_ret * side
    """
    if side == 0 or np.isnan(ret): return 0.0
    side_ret = side * ret
    if side_ret > tp: side_ret = tp
    if side_ret < -sl: side_ret = -sl
    return side_ret * side

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--signals-csv", required=True)
    ap.add_argument("--capital-initial", type=float, default=10_000.0)
    ap.add_argument("--fixed-cash", type=float, default=2_000.0)
    ap.add_argument("--tp-pct", type=float, default=0.08)
    ap.add_argument("--sl-pct", type=float, default=0.02)
    ap.add_argument("--horizon-days", type=int, default=3)
    ap.add_argument("--out-suffix", default="", help="Sufijo para nombres de salida (evita sobreescritura)")
    args = ap.parse_args()

    month = args.month
    inp = Path(args.signals_csv)
    if not inp.exists():
        raise FileNotFoundError(f"No existe signals CSV: {inp}")

    df = pd.read_csv(inp)

    # normaliza 'ticker' y 'date'
    for c in ("ticker", "date"):
        if c not in df.columns:
            cands = [x for x in df.columns if x.lower() == c]
            if cands: df = df.rename(columns={cands[0]: c})
    if "ticker" not in df.columns or "date" not in df.columns:
        raise ValueError("Se requieren columnas 'ticker' y 'date' en el CSV de señales.")

    # señal: preferimos 'signal'; si no, side/side_hat/y_hat
    if "signal" not in df.columns:
        if "side" in df.columns:
            df["signal"] = df["side"]
        elif "side_hat" in df.columns:
            df["signal"] = df["side_hat"]
        elif "y_hat" in df.columns:
            df["signal"] = np.where(df["y_hat"] >= 0, 1, -1)
        else:
            df["signal"] = 0

    # normaliza a {-1,0,1} usando fallback de side/side_hat (si existen)
    fallback_series = None
    for alt in ("side", "side_hat"):
        if alt in df.columns:
            fallback_series = df[alt]; break

    if fallback_series is not None:
        df["signal"] = [parse_signal(v, fb) for v, fb in zip(df["signal"], fallback_series)]
    else:
        df["signal"] = [parse_signal(v) for v in df["signal"]]

    # precio de entrada
    df["entry_price_eff"] = df.apply(pick_entry_price, axis=1)
    df = df.dropna(subset=["entry_price_eff"])

    # forward del horizonte
    fwd_col = f"Close_fwd_H{args.horizon_days}"
    out_dir = Path(f"reports/forecast/{month}"); out_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"__{args.out_suffix}" if args.out_suffix else ""
    out_trades = out_dir / f"trades_{month}{suffix}.csv"
    out_summary = out_dir / f"simulation_summary_{month}{suffix}.json"

    if fwd_col not in df.columns:
        print(f"⚠️  No existe {fwd_col} en {inp}. No se pueden valorar trades; archivo vacío.")
        trades = pd.DataFrame(columns=[
            "date","ticker","signal","entry_price_eff","exit_price_eff","ret_raw","ret_capped","shares","cash_alloc","cash_pnl"
        ])
        trades.to_csv(out_trades, index=False)
        out_summary.write_text(
            json.dumps({"rows": 0, "capital_final": args.capital_initial, "pnl": 0.0}, indent=2),
            encoding="utf-8"
        )
        return

    df = df.dropna(subset=[fwd_col])
    if df.empty:
        print(f"⚠️  {fwd_col} está vacío tras dropna; no hay trades valorables.")
        trades = pd.DataFrame(columns=[
            "date","ticker","signal","entry_price_eff","exit_price_eff","ret_raw","ret_capped","shares","cash_alloc","cash_pnl"
        ])
        trades.to_csv(out_trades, index=False)
        out_summary.write_text(
            json.dumps({"rows": 0, "capital_final": args.capital_initial, "pnl": 0.0}, indent=2),
            encoding="utf-8"
        )
        return

    # retorno al horizonte
    df["exit_price_raw"] = df[fwd_col].astype(float)
    df["ret_raw"] = (df["exit_price_raw"] - df["entry_price_eff"]) / df["entry_price_eff"]

    # cap TP/SL en retorno del lado
    df["ret_capped"] = [
        cap_with_tp_sl(r, int(s), args.tp_pct, args.sl_pct)
        for r, s in zip(df["ret_raw"], df["signal"])
    ]

    # trades activos
    trades = df[df["signal"] != 0].copy()
    if trades.empty:
        print("ℹ️  No hay señales != 0; no se generaron trades.")
        trades.to_csv(out_trades, index=False)
        out_summary.write_text(
            json.dumps({"rows": 0, "capital_final": args.capital_initial, "pnl": 0.0}, indent=2),
            encoding="utf-8"
        )
        return

    # tamaño por efectivo fijo
    trades["cash_alloc"] = float(args.fixed_cash)
    trades["shares"] = (trades["cash_alloc"] / trades["entry_price_eff"]).fillna(0.0)

    # precio de salida aproximado por retorno cappeado
    trades["exit_price_eff"] = trades["entry_price_eff"] * (1.0 + trades["ret_capped"])

    # P&L efectivo
    trades["cash_pnl"] = trades["shares"] * (trades["exit_price_eff"] - trades["entry_price_eff"])

    # outputs
    keep_cols = ["date","ticker","signal","entry_price_eff","exit_price_eff","ret_raw","ret_capped","shares","cash_alloc","cash_pnl"]
    trades[keep_cols].to_csv(out_trades, index=False)

    gross_pnl = float(trades["cash_pnl"].sum())
    capital_final = float(args.capital_initial + gross_pnl)

    summary = {
        "rows": int(len(trades)),
        "capital_initial": float(args.capital_initial),
        "capital_final": capital_final,
        "gross_pnl": gross_pnl,
        "tp_pct": float(args.tp_pct),
        "sl_pct": float(args.sl_pct),
        "horizon_days": int(args.horizon_days),
        "trades_csv": str(out_trades)
    }
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"✅ Simulación lista: {out_trades}")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
