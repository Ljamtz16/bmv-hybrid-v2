import argparse
import json
import os
from pathlib import Path
from typing import List

import pandas as pd


def find_month_dirs(base: Path, year: str) -> List[Path]:
    d = base / "reports" / "forecast"
    if not d.exists():
        return []
    out = []
    for child in sorted(d.iterdir()):
        if child.is_dir() and child.name.startswith(f"{year}-"):
            out.append(child)
    return out


def load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Aggregate monthly KPIs into a single CSV")
    parser.add_argument("--year", required=True, help="Year to aggregate, e.g., 2025")
    parser.add_argument(
        "--months",
        default=None,
        help="Optional comma-separated list of YYYY-MM to include. If omitted, auto-detects.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output CSV path. Default: reports/forecast/kpi_monthly_summary.csv",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    base = root

    # Determine months to include
    if args.months:
        month_dirs = [(base / "reports" / "forecast" / m) for m in args.months.split(",")]
    else:
        month_dirs = find_month_dirs(base, args.year)

    rows = []
    for mdir in month_dirs:
        kpi_path = mdir / "kpi_all.json"
        if not kpi_path.exists():
            continue
        kpi = load_json(kpi_path)

        # Optional counts for context
        sim_merged = (mdir / "simulate_results_merged.csv").exists()
        sim_all = (mdir / "simulate_results_all.csv").exists()
        trades_detailed = (mdir / "trades_detailed.csv").exists()

        sim_merged_rows = 0
        sim_all_rows = 0
        trades_detailed_rows = 0
        try:
            if sim_merged:
                sim_merged_rows = sum(1 for _ in open(mdir / "simulate_results_merged.csv", "r", encoding="utf-8")) - 1
        except Exception:
            pass
        try:
            if sim_all:
                sim_all_rows = sum(1 for _ in open(mdir / "simulate_results_all.csv", "r", encoding="utf-8")) - 1
        except Exception:
            pass
        try:
            if trades_detailed:
                trades_detailed_rows = sum(1 for _ in open(mdir / "trades_detailed.csv", "r", encoding="utf-8")) - 1
        except Exception:
            pass

        # Unique trades executed (prefer activity_metrics.json or kpi_all.json field)
        unique_trades_executed = None
        act_path = mdir / "activity_metrics.json"
        try:
            if act_path.exists():
                act = load_json(act_path)
                unique_trades_executed = act.get("unique_trades_executed")
        except Exception:
            pass
        if unique_trades_executed is None:
            unique_trades_executed = kpi.get("unique_trades_executed")

        rows.append(
            {
                "month": mdir.name,
                "win_rate": kpi.get("win_rate"),
                "net_pnl_sum": kpi.get("net_pnl_sum"),
                "capital_final": kpi.get("capital_final"),
                "trades": kpi.get("trades"),
                "unique_trades_executed": unique_trades_executed,
                "simulate_results_all_rows": sim_all_rows,
                "simulate_results_merged_rows": sim_merged_rows,
                "trades_detailed_rows": trades_detailed_rows,
            }
        )

    if not rows:
        print("No KPI data found.")
        return

    df = pd.DataFrame(rows).sort_values("month").reset_index(drop=True)
    # Totals row
    totals = {
        "month": "TOTAL",
        "win_rate": None,
        "net_pnl_sum": df["net_pnl_sum"].sum(min_count=1),
        "capital_final": None,
        "trades": df["trades"].sum(min_count=1),
        "unique_trades_executed": df["unique_trades_executed"].sum(min_count=1) if "unique_trades_executed" in df.columns else None,
        "simulate_results_all_rows": df["simulate_results_all_rows"].sum(min_count=1),
        "simulate_results_merged_rows": df["simulate_results_merged_rows"].sum(min_count=1),
        "trades_detailed_rows": df["trades_detailed_rows"].sum(min_count=1),
    }
    df_out = pd.concat([df, pd.DataFrame([totals])], ignore_index=True)

    out_path = (
        Path(args.out)
        if args.out
        else (base / "reports" / "forecast" / "kpi_monthly_summary.csv")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(out_path, index=False)
    print(f"[aggregate] Saved -> {out_path} (rows={len(df_out)})")
    # Print a compact preview
    print(df_out)


if __name__ == "__main__":
    main()
