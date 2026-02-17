import argparse
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def find_month_dirs(base: Path, year: str | None) -> List[Path]:
    root = base / "reports" / "forecast"
    if not root.exists():
        return []
    months = []
    for p in root.iterdir():
        if p.is_dir() and MONTH_RE.match(p.name):
            if year is None or p.name.startswith(f"{year}-"):
                months.append(p)
    return sorted(months)


def safe_load_json(path: Path) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def safe_count_rows(path: Path) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            # subtract header
            return max(sum(1 for _ in f) - 1, 0)
    except Exception:
        return 0


def aggregate_month(month_dir: Path) -> pd.DataFrame:
    history_dir = month_dir / "history"
    if not history_dir.exists():
        return pd.DataFrame()
    run_dirs = [d for d in history_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
    rows: List[Dict[str, Any]] = []
    for rdir in sorted(run_dirs):
        meta = safe_load_json(rdir / "run_metadata.json") or {}
        kpi_all = safe_load_json(rdir / "kpi_all.json") or {}

        row: Dict[str, Any] = {
            "run_id": meta.get("run_id", rdir.name.replace("run_", "")),
            "timestamp_utc": meta.get("timestamp_utc"),
            "autotune": meta.get("autotune"),
            "fallback_used": meta.get("fallback_used"),
            "min_prob": (meta.get("thresholds") or {}).get("min_prob"),
            "min_abs_yhat": (meta.get("thresholds") or {}).get("min_abs_yhat"),
            "per_trade_cash": meta.get("per_trade_cash"),
            "final_trades": meta.get("final_trades"),
            # KPI from snapshot
            "trades": kpi_all.get("trades"),
            "net_pnl_sum": kpi_all.get("net_pnl_sum"),
            "win_rate": kpi_all.get("win_rate"),
            "capital_final": kpi_all.get("capital_final"),
            # File-based row counts from snapshot
            "simulate_results_all_rows": safe_count_rows(rdir / "simulate_results_all.csv"),
            "simulate_results_merged_rows": safe_count_rows(rdir / "simulate_results_merged.csv"),
            "trades_detailed_rows": safe_count_rows(rdir / "trades_detailed.csv"),
        }
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Sort by timestamp if available, else run_id
    sort_cols = [c for c in ["timestamp_utc", "run_id"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df


def main():
    ap = argparse.ArgumentParser(description="Aggregate run history snapshots into per-month and global CSVs")
    ap.add_argument("--year", default=None, help="Optional year filter, e.g., 2025")
    ap.add_argument("--months", default=None, help="Optional comma-separated month list (YYYY-MM)")
    ap.add_argument("--out-global", default=None, help="Optional global output CSV (default: reports/forecast/kpi_runs_summary.csv)")
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    if args.months:
        month_dirs = [(base / "reports" / "forecast" / m) for m in args.months.split(",")]
    else:
        month_dirs = find_month_dirs(base, args.year)

    all_rows: List[pd.DataFrame] = []
    for mdir in month_dirs:
        if not mdir.exists():
            continue
        df = aggregate_month(mdir)
        if df.empty:
            continue
        # Write per-month CSV
        out_month = mdir / "kpi_runs.csv"
        df.to_csv(out_month, index=False)
        print(f"[runs] Saved per-month: {out_month} (rows={len(df)})")
        # Accumulate global
        df_g = df.copy()
        df_g.insert(0, "month", mdir.name)
        all_rows.append(df_g)

    if all_rows:
        df_all = pd.concat(all_rows, ignore_index=True)
        out_global = (
            Path(args.out_global)
            if args.out_global
            else (base / "reports" / "forecast" / "kpi_runs_summary.csv")
        )
        out_global.parent.mkdir(parents=True, exist_ok=True)
        df_all.to_csv(out_global, index=False)
        print(f"[runs] Saved global summary: {out_global} (rows={len(df_all)})")
    else:
        print("[runs] No run history found to aggregate.")


if __name__ == "__main__":
    main()
