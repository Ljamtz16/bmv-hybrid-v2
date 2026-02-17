#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Lee un grid_summary.csv (salida de 27_policy_gridsearch.py), toma el top-1 por NetPnL
y construye un policy JSON compatible con 26_policy_recompute_pnl.py.

Uso:
  python scripts/29_grid_pick_best.py \
    --grid-summary runs/2025-03_grid/grid_summary.csv \
    --out-json runs/policy_best_2025-03.json \
    --min-abs-y 0.06 \
    --per-trade-cash 2000 \
    --commission-side 5.0 \
    --long-only
"""

import argparse, json, os, sys
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid-summary", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--min-abs-y", type=float, default=0.06)
    ap.add_argument("--per-trade-cash", type=float, default=1000.0)
    ap.add_argument("--commission-side", type=float, default=5.0)
    ap.add_argument("--long-only", action="store_true", default=False)
    args = ap.parse_args()

    if not os.path.exists(args.grid_summary):
        print(f"[ERROR] No existe grid-summary: {args.grid_summary}")
        sys.exit(2)

    df = pd.read_csv(args.grid_summary)
    if df.empty:
        print("[ERROR] grid_summary.csv está vacío")
        sys.exit(3)

    # Buscamos columnas típicas del grid
    # Deben existir: tp_pct, sl_pct, horizon_days y net_pnl_sum
    cols_needed = {"tp_pct", "sl_pct", "horizon_days", "net_pnl_sum"}
    if not cols_needed.issubset(df.columns):
        print(f"[ERROR] Faltan columnas en grid_summary: {cols_needed - set(df.columns)}")
        print("Columnas disponibles:", list(df.columns))
        sys.exit(4)

    # Top-1 por NetPnL desc
    best = df.sort_values("net_pnl_sum", ascending=False).iloc[0]

    policy = {
        "tp_pct":       float(best["tp_pct"]),
        "sl_pct":       float(best["sl_pct"]),
        "horizon_days": int(best["horizon_days"]),
        "min_abs_y":    float(args.min_abs_y),
        "long_only":    bool(args.long_only),
        "per_trade_cash": float(args.per_trade_cash),
        "commission_side": float(args.commission_side),
    }

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(policy, f, ensure_ascii=False, indent=2)

    print(f"✅ policy best generado → {args.out_json}")
    print("Contenido:")
    print(json.dumps(policy, indent=2))

if __name__ == "__main__":
    main()
