
"""
simulate_trading.py — Simula PnL con reglas de trading y filtros opcionales:
- Señal BUY si y_pred > 0; SELL si y_pred < 0 (o solo BUY si --long-only).
- Filtro de fuerza de señal: --min-abs-y (no operar si |y_pred| < umbral).
- Entrada al día siguiente (D+1) a precio de Open.
- TP = +X% y SL = -Y% (BUY); para SELL, TP es -X% y SL es +Y%.
- Horizonte: revisar próximos N días (incluye el día de entrada como D0). Si no toca TP/SL, salida al Close del último día.
- Sizing: efectivo fijo por operación → shares = floor(cash / entry_price).
- Comisión: fija por lado (entrada y salida).

Salidas por mes:
- reports/forecast/<YYYY-MM>/validation/trades.csv
- reports/forecast/<YYYY-MM>/validation/pnl_summary.json
"""
import os, argparse, json, math, pandas as pd, numpy as np
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FROZEN = os.path.join(ROOT, "data", "frozen")
REPORTS = os.path.join(ROOT, "reports")

def load_price_series(ticker):
    path = os.path.join(FROZEN, f"{ticker}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe {path}. Corre freeze_data.py")
    df = pd.read_parquet(path)
    df = df.sort_values("Date").reset_index(drop=True)
    return df[["Date","Open","High","Low","Close"]].copy()

def simulate_month(month, fixed_cash=2000.0, tp_pct=0.05, sl_pct=0.02,
                   horizon_days=4, commission_side=5.0, capital_initial=10000.0,
                   min_abs_y=0.0, long_only=False):
    pred_path = os.path.join(REPORTS, "forecast", month, "validation", "predictions.csv")
    if not os.path.exists(pred_path):
        raise FileNotFoundError(f"No existe {pred_path} (corre make_month_forecast primero)")
    preds = pd.read_csv(pred_path, parse_dates=["Date"])
    if "Ticker" not in preds.columns:
        raise ValueError("predictions.csv debe incluir columna 'Ticker'")
    preds = preds.sort_values(["Ticker","Date"]).reset_index(drop=True)

    trades = []
    capital = capital_initial
    cache_prices = {}

    for _, row in preds.iterrows():
        ticker = row["Ticker"]
        signal_date = row["Date"]
        ypred = row["y_pred"]
        if pd.isna(ypred) or ypred == 0:
            continue
        if abs(ypred) < min_abs_y:
            continue
        if long_only and ypred < 0:
            continue

        if ticker not in cache_prices:
            cache_prices[ticker] = load_price_series(ticker)
        px = cache_prices[ticker]

        idx_arr = px.index[px["Date"] == signal_date]
        if len(idx_arr) == 0:
            continue
        i = int(idx_arr[0])

        entry_idx = i + 1
        if entry_idx >= len(px):
            continue
        entry_row = px.iloc[entry_idx]
        entry_date = entry_row["Date"]
        entry_price = float(entry_row["Open"])
        if entry_price <= 0 or not np.isfinite(entry_price):
            continue

        side = "BUY" if ypred > 0 else "SELL"
        shares = math.floor(fixed_cash / entry_price)
        if shares <= 0:
            continue

        if side == "BUY":
            tp_price = entry_price * (1 + tp_pct)
            sl_price = entry_price * (1 - sl_pct)
        else:
            tp_price = entry_price * (1 - tp_pct)
            sl_price = entry_price * (1 + sl_pct)

        exit_price = None
        exit_date = None
        outcome = "TIMEOUT"

        last_idx = min(entry_idx + horizon_days, len(px)-1)
        for j in range(entry_idx, last_idx+1):
            hi = float(px.iloc[j]["High"])
            lo = float(px.iloc[j]["Low"])
            day_date = px.iloc[j]["Date"]

            if side == "BUY":
                hit_tp = hi >= tp_price
                hit_sl = lo <= sl_price
            else:
                hit_tp = lo <= tp_price
                hit_sl = hi >= sl_price

            if hit_tp and hit_sl:
                outcome = "SL"
                exit_price = sl_price
                exit_date = day_date
                break
            elif hit_tp:
                outcome = "TP"
                exit_price = tp_price
                exit_date = day_date
                break
            elif hit_sl:
                outcome = "SL"
                exit_price = sl_price
                exit_date = day_date
                break

        if exit_price is None:
            exit_row = px.iloc[last_idx]
            exit_date = exit_row["Date"]
            exit_price = float(exit_row["Close"])
            outcome = "TIMEOUT"

        if side == "BUY":
            gross = (exit_price - entry_price) * shares
        else:
            gross = (entry_price - exit_price) * shares

        commission = commission_side * 2.0
        net = gross - commission
        capital += net

        trades.append({
            "Ticker": ticker,
            "signal_date": pd.to_datetime(signal_date),
            "side": side,
            "entry_date": pd.to_datetime(entry_date),
            "entry_price": entry_price,
            "shares": shares,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "exit_date": pd.to_datetime(exit_date),
            "exit_price": exit_price,
            "outcome": outcome,
            "gross_pnl": gross,
            "commission": commission,
            "net_pnl": net,
            "capital_after": capital,
            "y_pred": float(ypred)
        })

    trades_df = pd.DataFrame(trades)
    out_dir = os.path.join(REPORTS, "forecast", month, "validation")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    if len(trades_df) > 0:
        trades_df.to_csv(os.path.join(out_dir, "trades.csv"), index=False)

        summary = {
            "month": month,
            "trades": int(len(trades_df)),
            "tp_rate": float((trades_df["outcome"]=="TP").mean()),
            "sl_rate": float((trades_df["outcome"]=="SL").mean()),
            "timeout_rate": float((trades_df["outcome"]=="TIMEOUT").mean()),
            "gross_pnl_sum": float(trades_df["gross_pnl"].sum()),
            "net_pnl_sum": float(trades_df["net_pnl"].sum()),
            "capital_final": float(trades_df["capital_after"].iloc[-1]),
            "params": {
                "capital_initial": capital_initial,
                "fixed_cash_per_trade": fixed_cash,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "horizon_days": horizon_days,
                "commission_side": commission_side,
                "min_abs_y": min_abs_y,
                "long_only": long_only
            }
        }
    else:
        summary = {
            "month": month,
            "trades": 0,
            "tp_rate": 0.0,
            "sl_rate": 0.0,
            "timeout_rate": 0.0,
            "gross_pnl_sum": 0.0,
            "net_pnl_sum": 0.0,
            "capital_final": capital_initial,
            "params": {
                "capital_initial": capital_initial,
                "fixed_cash_per_trade": fixed_cash,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "horizon_days": horizon_days,
                "commission_side": commission_side,
                "min_abs_y": min_abs_y,
                "long_only": long_only
            }
        }

    with open(os.path.join(out_dir, "pnl_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("Simulación terminada. Resumen:", summary)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--capital-initial", type=float, default=10000.0)
    ap.add_argument("--fixed-cash", type=float, default=2000.0)
    ap.add_argument("--tp-pct", type=float, default=0.05)
    ap.add_argument("--sl-pct", type=float, default=0.02)
    ap.add_argument("--horizon-days", type=int, default=4)
    ap.add_argument("--commission-side", type=float, default=5.0)
    ap.add_argument("--min-abs-y", type=float, default=0.0, help="No operar si |y_pred| < este umbral (ej. 0.01 = 1%)")
    ap.add_argument("--long-only", action="store_true", help="Si se activa, solo BUY (ignora señales SELL)")
    args = ap.parse_args()

    simulate_month(
        month=args.month,
        fixed_cash=args.fixed_cash,
        tp_pct=args.tp_pct,
        sl_pct=args.sl_pct,
        horizon_days=args.horizon_days,
        commission_side=args.commission_side,
        capital_initial=args.capital_initial,
        min_abs_y=args.min_abs_y,
        long_only=args.long_only
    )
