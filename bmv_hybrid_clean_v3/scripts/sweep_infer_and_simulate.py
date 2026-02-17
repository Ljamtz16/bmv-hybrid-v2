#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Barrido de umbrales para inferencia + simulación.

- Para cada min_abs_y, genera un forecast_X.csv distinto
- Llama simulate_trading con un sufijo para NO sobreescribir archivos
- Consolida resultados en un CSV de resumen

Ejemplo:
  python scripts/sweep_infer_and_simulate.py \
    --month 2025-10 \
    --features reports/forecast/2025-10/features_labeled.csv \
    --model models/return_model_H3.joblib \
    --thresholds 0.04 0.05 0.06 0.07 \
    --tp 0.08 --sl 0.02 --H 3 \
    --outdir reports/forecast/2025-10
"""

import argparse, json, subprocess, sys
from pathlib import Path
import csv

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        raise RuntimeError(f"Error en: {' '.join(cmd)}")
    return p.stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--thresholds", nargs="+", type=float, required=True)
    ap.add_argument("--tp", type=float, default=0.08)
    ap.add_argument("--sl", type=float, default=0.02)
    ap.add_argument("--H", type=int, default=3)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--cash", type=float, default=2_000.0)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    outdir = Path(args.outdir or f"reports/forecast/{args.month}")
    outdir.mkdir(parents=True, exist_ok=True)
    summary_path = outdir / f"sweep_summary_{args.month}.csv"

    # header de resumen
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["min_abs_y","rows","capital_initial","capital_final","gross_pnl","tp_pct","sl_pct","H","signals_csv","trades_csv"])

    for thr in args.thresholds:
        thr_str = f"{thr:.2f}"
        signals_csv = outdir / f"forecast_{args.month}_with_gate_{thr_str}.csv"

        # 1) infer_and_gate con salida única por umbral
        cmd_infer = [
            sys.executable, "scripts/infer_and_gate.py",
            "--features-csv", args.features,
            "--out-csv", str(signals_csv),
            "--model", args.model,
            "--min-abs-y", str(thr),
        ]
        print(">>", " ".join(cmd_infer))
        run(cmd_infer)

        # 2) simulate_trading con sufijo para no pisar archivos
        #    añadimos --out-suffix para que el script nombre trades_<month>__thr_0.04.csv, etc.
        cmd_sim = [
            sys.executable, "scripts/simulate_trading.py",
            "--month", args.month,
            "--signals-csv", str(signals_csv),
            "--capital-initial", str(args.capital),
            "--fixed-cash", str(args.cash),
            "--tp-pct", str(args.tp),
            "--sl-pct", str(args.sl),
            "--horizon-days", str(args.H),
            "--out-suffix", f"thr_{thr_str}"
        ]
        print(">>", " ".join(cmd_sim))
        out = run(cmd_sim)

        # parsear el JSON del final (última línea con llaves)
        last_json = None
        for line in out.splitlines()[::-1]:
            if line.strip().startswith("{") and line.strip().endswith("}"):
                last_json = json.loads(line.strip())
                break
        if last_json is None:
            last_json = {}

        with open(summary_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                thr,
                last_json.get("rows"),
                last_json.get("capital_initial"),
                last_json.get("capital_final"),
                last_json.get("gross_pnl"),
                last_json.get("tp_pct"),
                last_json.get("sl_pct"),
                last_json.get("horizon_days"),
                str(signals_csv),
                last_json.get("trades_csv"),
            ])

    print(f"\n✅ Resumen guardado en: {summary_path}")

if __name__ == "__main__":
    main()
