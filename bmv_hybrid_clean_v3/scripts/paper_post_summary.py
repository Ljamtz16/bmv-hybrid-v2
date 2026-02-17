# scripts/paper_post_summary.py
from __future__ import annotations

import json
import glob
from pathlib import Path
import pandas as pd
import numpy as np


def max_drawdown(equity: pd.Series) -> float:
    """Devuelve el Max Drawdown (positivo)."""
    if equity.empty:
        return 0.0
    roll_max = equity.cummax()
    dd = equity - roll_max
    return float(-dd.min())


def sharpe_from_pnl(pnl: pd.Series) -> float:
    """Sharpe aprox usando pnl por día (annualizado con sqrt(252))."""
    if pnl.empty:
        return 0.0
    mu = pnl.mean()
    sigma = pnl.std(ddof=1)
    if sigma == 0:
        return 0.0
    return float(mu / sigma * np.sqrt(252))


def main():
    reports_root = Path("reports")
    paper_dir = reports_root / "paper_trading"

    eq_csv = paper_dir / "paper_daily_equity.csv"
    if not eq_csv.exists():
        print(f"⚠️ No encontré {eq_csv}. Corre primero paper_run_daily.py con --dump.")
        return

    # === Curva diaria (solo métricas, sin gráficos) ===
    df = pd.read_csv(eq_csv, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if not {"pnl", "equity"}.issubset(df.columns):
        print(f"⚠️ {eq_csv} no tiene columnas requeridas (pnl, equity).")
        return

    pnl = df["pnl"].astype(float)
    equity = df["equity"].astype(float)

    metrics = {
        "start_date": df["date"].iloc[0].strftime("%Y-%m-%d") if not df.empty else None,
        "end_date": df["date"].iloc[-1].strftime("%Y-%m-%d") if not df.empty else None,
        "days": int(df.shape[0]),
        "final_equity": float(equity.iloc[-1]) if not equity.empty else 0.0,
        "max_drawdown": max_drawdown(equity),
        "sharpe_approx": sharpe_from_pnl(pnl),
        "expectancy_per_day": float(pnl.mean()) if not pnl.empty else 0.0,
        "avg_trades_per_day": float(df["trades"].mean()) if "trades" in df.columns else None,
    }

    metrics_path = paper_dir / "paper_daily_equity_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Métricas de equity guardadas en: {metrics_path}")

    # === Unir trades diarios (de subcarpetas YYYY-MM-DD) ===
    trade_glob = str(paper_dir / "*" / "trades_*.csv")
    files = glob.glob(trade_glob)

    if not files:
        print("ℹ️ No encontré trades diarios en subcarpetas (¿corrió paper_run_daily.py con --dump?).")
        print("   Se generan solo las métricas de equity.")
        return

    trades = []
    for f in files:
        try:
            tmp = pd.read_csv(f)
            trades.append(tmp)
        except Exception as e:
            print(f"⚠️ No pude leer {f}: {e}")

    if not trades:
        print("⚠️ No había archivos de trades válidos.")
        return

    trades_df = pd.concat(trades, ignore_index=True)

    # Normalizar columnas mínimas
    for col in ["ticker", "pnl", "side", "date"]:
        if col not in trades_df.columns:
            trades_df[col] = None
    trades_df["pnl"] = pd.to_numeric(trades_df["pnl"], errors="coerce").fillna(0.0)
    trades_df["date"] = pd.to_datetime(trades_df["date"], errors="coerce")
    trades_df = trades_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # === Resumen por ticker ===
    by_ticker = trades_df.groupby("ticker", dropna=False).agg(
        trades=("pnl", "count"),
        pnl_sum=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100.0),
    ).reset_index().sort_values("pnl_sum", ascending=False)

    out_by_ticker = paper_dir / "paper_trades_by_ticker.csv"
    by_ticker.to_csv(out_by_ticker, index=False, encoding="utf-8")
    print(f"✅ Atribución por ticker → {out_by_ticker}")

    # === Resumen diario (desde trades) para cotejar con equity ===
    by_day = trades_df.groupby(trades_df["date"].dt.strftime("%Y-%m-%d")).agg(
        trades=("pnl", "count"),
        pnl_sum=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100.0),
    ).reset_index().rename(columns={"date": "day"})

    out_by_day = paper_dir / "paper_day_summary.csv"
    by_day.to_csv(out_by_day, index=False, encoding="utf-8")
    print(f"✅ Resumen diario (desde trades) → {out_by_day}")

    # === Micro-resumen consola ===
    top_tickers = by_ticker.head(5)
    print("\n— Resumen rápido —")
    print(f"Equity final: {metrics['final_equity']:.2f} | MDD: {metrics['max_drawdown']:.2f} "
          f"| Sharpe≈ {metrics['sharpe_approx']:.2f} | Expect/day: {metrics['expectancy_per_day']:.2f}")
    if not top_tickers.empty:
        print("Top tickers por PnL:")
        for _, r in top_tickers.iterrows():
            t = r["ticker"] if pd.notna(r["ticker"]) else "(NA)"
            print(f"  - {t}: pnl_sum={r['pnl_sum']:.2f}, trades={int(r['trades'])}, win%={r['win_rate']:.1f}")


if __name__ == "__main__":
    main()
 