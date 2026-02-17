import argparse
import pandas as pd
import numpy as np
from pathlib import Path

# Simple helpers
GREEN = "GANANDO"
YELLOW = "Cerca del SL"
RED = "PERDIENDO"


def load_trades(month_dir: Path, trades_filename: str = "") -> pd.DataFrame:
    # Prefer explicit filename, else enriched if available (has entry/exit prices), else default
    if trades_filename:
        trades_path = month_dir / trades_filename
    else:
        enriched = month_dir / "trades_detailed_enriched.csv"
        trades_path = enriched if enriched.exists() else (month_dir / "trades_detailed.csv")
    df = pd.read_csv(trades_path)
    # normalize column names
    cols = {c: c.lower() for c in df.columns}
    df.rename(columns=cols, inplace=True)
    return df


def load_prices() -> pd.DataFrame:
    df = pd.read_csv("data/us/ohlcv_us_daily.csv", parse_dates=["date"])  # ticker,date,open,high,low,close,volume
    # ensure ticker is string
    df["ticker"] = df["ticker"].astype(str)
    return df


def compute_status(trades: pd.DataFrame, prices: pd.DataFrame, as_of: str) -> pd.DataFrame:
    # build latest price for as_of per ticker
    px = prices[prices["date"] == pd.to_datetime(as_of)].copy()
    last = px.set_index("ticker")["close"]

    rows = []
    for _, t in trades.iterrows():
        tk = t["ticker"]
        entry = float(t["entry_price"]) if "entry_price" in t else float(t.get("entry", np.nan))
        tp_pct = float(t.get("tp_pct", t.get("tp_pct_suggested", 0.065)))
        sl_pct = float(t.get("sl_pct", t.get("sl_pct_suggested", 0.008)))
        actual = float(last.get(tk, np.nan))
        if np.isnan(actual):
            # if as_of not present, try latest available
            px_t = prices[prices["ticker"] == tk].sort_values("date")
            if not px_t.empty:
                actual = float(px_t.iloc[-1]["close"])  # fallback
        cambio_pct = (actual / entry - 1.0) if entry and actual else np.nan
        tp_price = entry * (1 + tp_pct)
        sl_price = entry * (1 - sl_pct)
        # distances
        to_tp_pct = (tp_price / actual - 1.0) if actual else np.nan
        to_sl_pct = (actual / sl_price - 1.0) if sl_price else np.nan
        # status
        if np.isnan(cambio_pct):
            estado = "SIN PRECIO"
        elif cambio_pct >= 0:
            # near SL if distance to SL < 1%
            estado = GREEN if to_sl_pct is None or to_sl_pct > 0.01 else YELLOW
        else:
            estado = YELLOW if (actual - sl_price) / entry <= 0.01 else RED

        rows.append({
            "Ticker": tk,
            "Entrada": round(entry, 2),
            "Actual": round(actual, 2) if actual else np.nan,
            "Cambio": cambio_pct,
            "TP_Target": round(tp_price, 2),
            "SL": round(sl_price, 2),
            "Estado": estado,
            "Falta_TP_pct": to_tp_pct,
            "Margen_SL_pct": to_sl_pct,
        })
    out = pd.DataFrame(rows)
    return out


def fmt_pct(x, plus=True):
    if pd.isna(x):
        return "—"
    s = f"{x*100:.2f}%"
    if plus and x >= 0:
        s = "+" + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM of trades folder to read")
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD price date to compare against")
    ap.add_argument("--tickers", default="", help="Comma separated list of tickers to include (optional)")
    ap.add_argument("--tickers-file", default="", help="CSV with column 'ticker' to include (optional)")
    ap.add_argument("--trades-file", default="", help="Trades filename inside month folder (default auto)")
    args = ap.parse_args()

    month_dir = Path("reports/forecast") / args.month
    if not month_dir.exists():
        raise SystemExit(f"No existe carpeta {month_dir}")

    trades = load_trades(month_dir, args.trades_file)
    # optional filter by tickers
    tickers_set = set()
    if args.tickers:
        tickers_set |= {t.strip().upper() for t in args.tickers.split(',') if t.strip()}
    if args.tickers_file:
        try:
            tdf = pd.read_csv(args.tickers_file)
            tickers_set |= set(tdf['ticker'].astype(str).str.upper())
        except Exception:
            pass
    if tickers_set:
        trades = trades[trades['ticker'].astype(str).str.upper().isin(tickers_set)].copy()
    if trades.empty:
        print("No hay trades en el mes indicado. Ejecuta la simulación o relaja filtros.")
        return
    prices = load_prices()
    status_df = compute_status(trades, prices, args.as_of)

    # Print table similar to screenshot
    print("\n📈 Estado de tus Predicciones (", args.as_of, ")\n", sep="")
    disp = status_df[["Ticker", "Entrada", "Actual", "Cambio", "TP_Target", "SL", "Estado"]].copy()
    disp["Cambio"] = disp["Cambio"].apply(fmt_pct)
    print(disp.to_string(index=False))

    # Detailed notes
    print("\nAnálisis Detallado:")
    for _, r in status_df.iterrows():
        print(f"\n• {r['Ticker']} - {'Posición Positiva' if r['Estado']==GREEN else ('En Riesgo' if r['Estado']==YELLOW else 'Negativa')}")
        if not pd.isna(r['Actual']) and not pd.isna(r['Entrada']):
            change_abs = r['Actual'] - r['Entrada']
            print(f"  - Ganancia/Pérdida actual: ${change_abs:.2f} ({fmt_pct((r['Actual']/r['Entrada']-1), plus=True)})")
            print(f"  - Falta para TP: {fmt_pct(r['Falta_TP_pct'], plus=True)}")
            print(f"  - Margen sobre SL: {fmt_pct(r['Margen_SL_pct'], plus=True)}")
            print(f"  - Estatus: {r['Estado']}")

    # Summary
    pos = (status_df['Cambio'] >= 0).sum()
    neg = (status_df['Cambio'] < 0).sum()
    total = len(status_df)
    pnl_est = (status_df['Actual'] - status_df['Entrada']).sum()
    print("\nResumen:")
    print(f"  • {pos} de {total} operaciones en positivo")
    print(f"  • {neg} en negativo")
    print(f"  • PnL neto (mark-to-market): ${pnl_est:.2f}")

if __name__ == "__main__":
    main()
