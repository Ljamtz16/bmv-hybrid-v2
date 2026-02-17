#!/usr/bin/env python3
"""
Runner histórico para simulaciones PROBWIN_55.
Genera trades.csv, metrics.json, equity_curve.csv y weekly_summary.*
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

import backtest_comparative_modes as bcm


def _resolve_pnl_col(df: pd.DataFrame) -> str:
    pnl_col = bcm.resolve_pnl_col(df)
    return pnl_col if pnl_col else "pnl"


def _compute_weekly_summary(trades_df: pd.DataFrame, pnl_col: str, date_col: str = "exit_date") -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame(columns=[
            "week_start", "week_end", "trades", "pnl", "win_rate", "pf",
            "wins", "losses"
        ])

    df = trades_df.copy()
    if date_col not in df.columns:
        date_col = "entry_date" if "entry_date" in df.columns else None

    if not date_col:
        return pd.DataFrame(columns=[
            "week_start", "week_end", "trades", "pnl", "win_rate", "pf",
            "wins", "losses"
        ])

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    if df.empty:
        return pd.DataFrame(columns=[
            "week_start", "week_end", "trades", "pnl", "win_rate", "pf",
            "wins", "losses"
        ])

    df["week_start"] = df[date_col].dt.to_period("W-MON").apply(lambda r: r.start_time.date())
    df["week_end"] = df[date_col].dt.to_period("W-MON").apply(lambda r: r.end_time.date())

    rows = []
    for week_start, wdf in df.groupby("week_start"):
        pnl = float(wdf[pnl_col].fillna(0).sum())
        wins = int((wdf[pnl_col] > 0).sum())
        losses = int((wdf[pnl_col] <= 0).sum())
        trades = int(len(wdf))
        win_rate = wins / trades if trades else 0.0
        gross_profit = float(wdf.loc[wdf[pnl_col] > 0, pnl_col].sum()) if wins else 0.0
        gross_loss = float(-wdf.loc[wdf[pnl_col] < 0, pnl_col].sum()) if losses else 0.0
        pf = gross_profit / gross_loss if gross_loss > 0 else (1.0 if gross_profit > 0 else 0.0)

        rows.append({
            "week_start": week_start,
            "week_end": wdf["week_end"].iloc[0],
            "trades": trades,
            "pnl": pnl,
            "win_rate": win_rate,
            "pf": pf,
            "wins": wins,
            "losses": losses,
        })

    return pd.DataFrame(rows).sort_values("week_start")


def _compute_metrics(trades_df: pd.DataFrame, capital: float, mode: str) -> dict:
    pnl_col = _resolve_pnl_col(trades_df)
    if pnl_col not in trades_df.columns:
        total_pnl = 0.0
        n_trades = int(len(trades_df))
        win_rate = 0.0
        profit_factor = 0.0
        avg_pnl = 0.0
    else:
        total_pnl = float(trades_df[pnl_col].fillna(0).sum())
        n_trades = int(len(trades_df))
        wins = int((trades_df[pnl_col] > 0).sum())
        losses = int((trades_df[pnl_col] <= 0).sum())
        win_rate = wins / n_trades if n_trades > 0 else 0.0
        gains = trades_df.loc[trades_df[pnl_col] > 0, pnl_col].sum()
        losses_sum = -trades_df.loc[trades_df[pnl_col] < 0, pnl_col].sum()
        profit_factor = float(gains / losses_sum) if losses_sum > 0 else (float("inf") if gains > 0 else 0.0)
        avg_pnl = float(total_pnl / n_trades) if n_trades > 0 else 0.0

    final_equity = capital + total_pnl
    total_return = (final_equity - capital) / capital if capital else 0.0

    return {
        "mode": mode,
        "total_pnl": float(total_pnl),
        "return_pct": float(total_return * 100),
        "final_equity": float(final_equity),
        "n_trades": int(n_trades),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor if profit_factor != float("inf") else 9999.0),
        "avg_pnl_per_trade": float(avg_pnl),
        "capital": float(capital),
    }


def _normalize_intraday_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    if "entry_date" not in df.columns:
        if "entry_time" in df.columns:
            df["entry_date"] = pd.to_datetime(df["entry_time"], errors="coerce").dt.date
        elif "trade_date" in df.columns:
            df["entry_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date

    if "exit_date" not in df.columns:
        if "exit_time" in df.columns:
            df["exit_date"] = pd.to_datetime(df["exit_time"], errors="coerce").dt.date
        elif "entry_date" in df.columns:
            df["exit_date"] = df["entry_date"]

    return df


def _serialize_week_row(row_dict: dict) -> dict:
    cleaned = {}
    for key, value in row_dict.items():
        if hasattr(value, "isoformat"):
            cleaned[key] = value.isoformat()
        else:
            cleaned[key] = value
    return cleaned


def _write_weekly_summary(weekly_df: pd.DataFrame, output_dir: Path, prefix: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    weekly_csv = output_dir / f"weekly_summary_{prefix}.csv"
    weekly_df.to_csv(weekly_csv, index=False)

    best_week = weekly_df.iloc[weekly_df["pnl"].idxmax()].to_dict() if not weekly_df.empty else {}
    worst_week = weekly_df.iloc[weekly_df["pnl"].idxmin()].to_dict() if not weekly_df.empty else {}

    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_weeks": int(len(weekly_df)),
        "positive_weeks": int((weekly_df["pnl"] > 0).sum()) if not weekly_df.empty else 0,
        "negative_weeks": int((weekly_df["pnl"] < 0).sum()) if not weekly_df.empty else 0,
        "zero_trade_weeks": int((weekly_df["trades"] == 0).sum()) if not weekly_df.empty else 0,
        "avg_weekly_pnl": float(weekly_df["pnl"].mean()) if not weekly_df.empty else 0.0,
        "std_weekly_pnl": float(weekly_df["pnl"].std()) if not weekly_df.empty else 0.0,
        "best_week": _serialize_week_row(best_week),
        "worst_week": _serialize_week_row(worst_week),
    }

    weekly_json = output_dir / f"weekly_summary_{prefix}.json"
    weekly_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_simulation(start_date: str, end_date: str, pw_threshold: float, output_dir: Path,
                   ticker_universe: str | None, forecast_path: str | None,
                   intraday_trades_path: str | None, capital: float,
                   intraday_capital: float) -> None:
    bcm.START_DATE = start_date
    bcm.END_DATE = end_date

    tickers = None
    if ticker_universe:
        tickers = [t.strip().upper() for t in ticker_universe.split(",") if t.strip()]

    intraday_df, daily_df, forecast_df = bcm.load_data(
        mode="probwin_only",
        forecast_path=forecast_path or bcm.FORECAST_FILE,
        ticker_universe=tickers
    )

    trades_df, final_equity, equity_curve = bcm.run_backtest(
        "probwin_only",
        intraday_df,
        daily_df,
        forecast_df,
        pw_threshold=pw_threshold
    )

    trades_df = bcm.ensure_trade_schema(trades_df)
    metrics_swing = bcm.analyze_results(trades_df, final_equity, "probwin_only")

    output_dir.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(output_dir / "trades_swing.csv", index=False)
    trades_df.to_csv(output_dir / "trades.csv", index=False)
    if equity_curve:
        pd.DataFrame(equity_curve).to_csv(output_dir / "equity_curve.csv", index=False)
    (output_dir / "metrics_swing.json").write_text(json.dumps(metrics_swing, indent=2), encoding="utf-8")

    intraday_trades_df = pd.DataFrame()
    metrics_intraday = _compute_metrics(intraday_trades_df, intraday_capital, "intraday")
    if intraday_trades_path:
        intraday_path = Path(intraday_trades_path)
        if intraday_path.exists():
            intraday_trades_df = pd.read_csv(intraday_path)
            intraday_trades_df = _normalize_intraday_trades(intraday_trades_df)
            metrics_intraday = _compute_metrics(intraday_trades_df, intraday_capital, "intraday")

    trades_total = pd.concat([trades_df, intraday_trades_df], ignore_index=True)
    metrics_total = _compute_metrics(trades_total, capital, "total")
    (output_dir / "metrics_intraday.json").write_text(json.dumps(metrics_intraday, indent=2), encoding="utf-8")
    (output_dir / "metrics_total.json").write_text(json.dumps(metrics_total, indent=2), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics_total, indent=2), encoding="utf-8")

    if not intraday_trades_df.empty:
        (output_dir / "trades_intraday.csv").write_text(
            intraday_trades_df.to_csv(index=False),
            encoding="utf-8"
        )
    trades_total.to_csv(output_dir / "trades_total.csv", index=False)

    pnl_col = _resolve_pnl_col(trades_df)
    weekly_swing = _compute_weekly_summary(trades_df, pnl_col)
    _write_weekly_summary(weekly_swing, output_dir, "swing")

    weekly_intraday = _compute_weekly_summary(intraday_trades_df, _resolve_pnl_col(intraday_trades_df))
    _write_weekly_summary(weekly_intraday, output_dir, "intraday")

    weekly_total = _compute_weekly_summary(trades_total, _resolve_pnl_col(trades_total))
    _write_weekly_summary(weekly_total, output_dir, "total")

    metadata = {
        "generated_at": datetime.now().isoformat(),
        "mode": "probwin_only",
        "pw_threshold": pw_threshold,
        "start_date": start_date,
        "end_date": end_date,
        "ticker_universe": tickers or "ALL",
        "forecast_path": str(forecast_path or bcm.FORECAST_FILE),
        "output_dir": str(output_dir),
        "capital": capital,
        "intraday_capital": intraday_capital,
        "intraday_trades_path": str(intraday_trades_path) if intraday_trades_path else None,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Runner histórico PROBWIN_55 (Phase 2) ")
    parser.add_argument("--start-date", default="2022-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--pw-threshold", type=float, default=0.55, help="ProbWin threshold")
    parser.add_argument("--ticker-universe", default=None, help="Comma-separated tickers")
    parser.add_argument("--forecast", default=None, help="Override forecast path")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--intraday-trades", default=None, help="CSV con trades intraday a combinar")
    parser.add_argument("--capital", type=float, default=2000.0, help="Capital total")
    parser.add_argument("--intraday-capital", type=float, default=None, help="Capital intraday (default 30% del total)")

    args = parser.parse_args()

    if args.output:
        output_dir = Path(args.output)
    else:
        suffix = f"probwin55_{args.start_date}_to_{args.end_date}".replace(":", "-")
        output_dir = Path("evidence") / "phase2_simulations" / suffix

    intraday_capital = args.intraday_capital if args.intraday_capital is not None else args.capital * 0.30

    run_simulation(
        start_date=args.start_date,
        end_date=args.end_date,
        pw_threshold=args.pw_threshold,
        output_dir=output_dir,
        ticker_universe=args.ticker_universe,
        forecast_path=args.forecast,
        intraday_trades_path=args.intraday_trades,
        capital=args.capital,
        intraday_capital=intraday_capital,
    )


if __name__ == "__main__":
    main()
