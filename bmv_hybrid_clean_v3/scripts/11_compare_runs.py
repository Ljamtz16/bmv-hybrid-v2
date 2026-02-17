# scripts/11_compare_runs.py
from __future__ import annotations

import argparse, os, glob, json
from pathlib import Path
import string
import pandas as pd
import numpy as np


def month_range(ym: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    y, m = map(int, ym.split("-"))
    start = pd.Timestamp(year=y, month=m, day=1)
    end = start + pd.offsets.MonthBegin(1)  # primer día del mes siguiente (excluyente)
    return start, end


def kpis_from_trades(trades: pd.DataFrame) -> dict:
    if trades is None or trades.empty:
        return {"Trades": 0, "WinRate_%": 0.0, "PnL_sum": 0.0, "MDD": 0.0, "Sharpe": 0.0, "Expectancy": 0.0}
    t = int(trades.shape[0])
    win = float((trades["pnl"] > 0).mean() * 100.0)
    pnl = float(trades["pnl"].sum())

    eq = trades["pnl"].cumsum()
    dd = eq - eq.cummax()
    mdd = float(-dd.min()) if len(dd) else 0.0

    ret = trades["pnl"]
    sharpe = float(ret.mean() / (ret.std(ddof=1) + 1e-12) * np.sqrt(252)) if len(ret) else 0.0
    expect = float(ret.mean()) if len(ret) else 0.0

    return {
        "Trades": t,
        "WinRate_%": round(win, 2),
        "PnL_sum": round(pnl, 2),
        "MDD": round(mdd, 2),
        "Sharpe": round(sharpe, 2),
        "Expectancy": round(expect, 2),
    }


def load_forecast_validation_month(ym: str, root: Path) -> pd.DataFrame | None:
    # reports/forecast/<YYYY-MM>/validation/validation_trades_auto.csv
    f = root / "forecast" / ym / "validation" / "validation_trades_auto.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_paper_trades_month(ym: str, root: Path) -> pd.DataFrame | None:
    # concatena todos los trades diarios guardados con --dump
    start, end = month_range(ym)
    # patrón: reports/paper_trading/<YYYY-MM-DD>/trades_*.csv
    files = glob.glob(str(root / "paper_trading" / "*" / "trades_*.csv"))
    if not files:
        return None
    chunks = []
    for p in files:
        try:
            df = pd.read_csv(p)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df[(df["date"] >= start) & (df["date"] < end)]
                if not df.empty:
                    chunks.append(df)
        except Exception:
            pass
    if not chunks:
        return None
    return pd.concat(chunks, ignore_index=True)


def load_backtest_month(ym: str, csv_paths: list[str]) -> pd.DataFrame | None:
    if not csv_paths:
        return None
    start, end = month_range(ym)
    chunks = []
    for p in csv_paths:
        f = Path(p)
        if not f.exists(): 
            continue
        try:
            df = pd.read_csv(f)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df[(df["date"] >= start) & (df["date"] < end)]
                if not df.empty:
                    chunks.append(df)
        except Exception:
            pass
    if not chunks:
        return None
    return pd.concat(chunks, ignore_index=True)


def parse_args():
    ap = argparse.ArgumentParser(
        description="Compara KPIs por mes entre forecast+validación, paper trading y (opcional) backtests."
    )
    ap.add_argument("--months", required=True,
                    help='Meses separados por coma o rango "YYYY-MM:YYYY-MM" (incluye ambos extremos).')
    ap.add_argument("--reports_dir", default="reports", help="Raíz de reports/")
    ap.add_argument("--backtest_csv", default="", 
                    help="Rutas a uno o más CSVs de trades (separadas por coma) para incluir como 'backtest'.")
    ap.add_argument("--out", default="reports/compare", help="Directorio de salida.")
    return ap.parse_args()


def expand_months(spec: string) -> list[str]:
    spec = spec.strip()
    if ":" in spec:
        a, b = spec.split(":")
        a = pd.Period(a.strip(), freq="M")
        b = pd.Period(b.strip(), freq="M")
        months = [str(p) for p in pd.period_range(a, b, freq="M")]
        return months
    return [m.strip() for m in spec.split(",") if m.strip()]


def main():
    args = parse_args()
    months = expand_months(args.months)
    root = Path(args.reports_dir)
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    backtest_csvs = [p for p in args.backtest_csv.split(",") if p.strip()]

    rows = []
    for ym in months:
        # 1) Forecast+validación
        v = load_forecast_validation_month(ym, root)
        if v is not None and not v.empty:
            k = kpis_from_trades(v)
            k.update(dict(month=ym, source="forecast_validation"))
            rows.append(k)

        # 2) Paper
        p = load_paper_trades_month(ym, root)
        if p is not None and not p.empty:
            k = kpis_from_trades(p)
            k.update(dict(month=ym, source="paper_trading"))
            rows.append(k)

        # 3) Backtest (si lo pasaron)
        b = load_backtest_month(ym, backtest_csvs)
        if b is not None and not b.empty:
            k = kpis_from_trades(b)
            k.update(dict(month=ym, source="backtest"))
            rows.append(k)

    if not rows:
        print("⚠️ No encontré datos para los meses indicados.")
        return

    df = pd.DataFrame(rows).sort_values(["month", "PnL_sum", "Sharpe"], ascending=[True, False, False])
    out_csv = out_dir / "compare_summary.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")

    # print resumen bonito
    print(f"\n✅ Comparativa lista → {out_csv}\n")
    for m in df["month"].unique():
        block = df[df["month"] == m].copy()
        print(f"— {m} —")
        for _, r in block.iterrows():
            print(f"  {r['source']:>20}: Trades={int(r['Trades'])} | Win%={r['WinRate_%']:.2f} | "
                  f"PnL={r['PnL_sum']:.2f} | MDD={r['MDD']:.2f} | Sharpe={r['Sharpe']:.2f}")
        print()

if __name__ == "__main__":
    main()
