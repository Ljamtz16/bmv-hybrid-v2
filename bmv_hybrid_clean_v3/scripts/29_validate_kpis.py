# scripts/29_validate_kpis.py
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

REQUIRED_FIELDS = [
    "trades",
    "net_pnl_sum",
    "gross_pnl_sum",
    "tp_rate",
    "sl_rate",
    "horizon_rate",
    "tp_pct",
    "sl_pct",
    "horizon_days",
    "per_trade_cash",
]

def load_json(p: Path) -> Optional[Dict[str, Any]]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] No pude leer {p}: {e}", file=sys.stderr)
        return None

def pct_fmt(x: float) -> str:
    return f"{x*100:.1f}%"

def round2(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(float(x), 2)

def check_schema(k: Dict[str, Any], src: Path) -> List[str]:
    errs = []
    for f in REQUIRED_FIELDS:
        if f not in k:
            errs.append(f"Falta campo '{f}' en {src}")
    # Rangos básicos (si existen)
    for f in ["tp_rate", "sl_rate", "horizon_rate"]:
        if f in k:
            v = k[f]
            if not (0.0 - 1e-9 <= float(v) <= 1.0 + 1e-9):
                errs.append(f"{f} fuera de [0,1] en {src}: {v}")
    for f in ["tp_pct", "sl_pct"]:
        if f in k and not (0.0 <= float(k[f]) <= 1.0):
            errs.append(f"{f} fuera de [0,1] en {src}: {k[f]}")
    if "trades" in k and int(k["trades"]) < 0:
        errs.append(f"trades negativo en {src}: {k['trades']}")
    if "horizon_days" in k and int(k["horizon_days"]) <= 0:
        errs.append(f"horizon_days <= 0 en {src}: {k['horizon_days']}")
    return errs

def compare(a: Dict[str, Any], b: Dict[str, Any], tol: float) -> List[str]:
    diffs = []
    numeric_keys = ["net_pnl_sum", "gross_pnl_sum", "trades",
                    "tp_rate", "sl_rate", "horizon_rate", "tp_pct", "sl_pct"]
    for k in numeric_keys:
        if k in a and k in b:
            va, vb = float(a[k]), float(b[k])
            if abs(va - vb) > tol:
                diffs.append(f"{k}: reports={va:.4f} vs runs={vb:.4f} | Δ={va-vb:+.4f}")
    return diffs

def parse_args():
    ap = argparse.ArgumentParser(description="Validador y resumen de KPIs por mes.")
    ap.add_argument("--months", nargs="+", required=True,
                    help='Lista de meses, ej: 2025-01 2025-02 ...')
    ap.add_argument("--repo-root", default=".",
                    help="Raíz del repo (default: .)")
    ap.add_argument("--compare-runs", action="store_true",
                    help="Comparar contra runs/kpi_policy_best_<MES>.json si existe.")
    ap.add_argument("--tolerance", type=float, default=1e-6,
                    help="Tolerancia absoluta para comparar números (default 1e-6).")
    ap.add_argument("--fail-on-missing", action="store_true",
                    help="Salir con error si falta algún JSON.")
    ap.add_argument("--csv-out", default=None,
                    help="Ruta opcional para exportar CSV con el resumen.")
    return ap.parse_args()

def main():
    args = parse_args()
    root = Path(args.repo_root).resolve()

    rows = []
    any_error = False

    print()
    print("Month    Trades  NetPnL_MXN  GrossPnL_MXN  TP_Rate  SL_Rate  H_Rate  TP_pct  SL_pct  H_days  CashPerTrade  Notes")
    print("-----    ------  ----------  ------------  -------  -------  ------  ------  ------  ------  ------------  -----")

    for m in args.months:
        rep_json = root / f"reports/forecast/{m}/validation/kpi_policy.json"
        k = load_json(rep_json)
        notes = []

        if k is None:
            notes.append("missing_reports")
            if args.fail_on_missing:
                print(f"[ERROR] Falta {rep_json}", file=sys.stderr)
                any_error = True
                continue
        else:
            errs = check_schema(k, rep_json)
            if errs:
                any_error = True
                for e in errs:
                    print(f"[ERROR] {e}", file=sys.stderr)

        # Comparación con runs (opcional)
        if args.compare_runs:
            runs_json = root / f"runs/kpi_policy_best_{m}.json"
            r = load_json(runs_json)
            if r is None:
                notes.append("missing_runs")
            else:
                diffs = compare(k or {}, r, args.tolerance)
                if diffs:
                    notes.append("DIFF:" + " | ".join(diffs))

        # Fila de salida
        if k:
            row = {
                "Month": m,
                "Trades": int(k["trades"]),
                "NetPnL_MXN": round2(k["net_pnl_sum"]),
                "GrossPnL_MXN": round2(k["gross_pnl_sum"]),
                "TP_Rate": pct_fmt(float(k["tp_rate"])),
                "SL_Rate": pct_fmt(float(k["sl_rate"])),
                "H_Rate": pct_fmt(float(k["horizon_rate"])),
                "TP_pct": pct_fmt(float(k["tp_pct"])),
                "SL_pct": pct_fmt(float(k["sl_pct"])),
                "H_days": int(k["horizon_days"]),
                "CashPerTrade": float(k["per_trade_cash"]),
                "Notes": ";".join(notes) if notes else ""
            }
            rows.append(row)
            print(f"{m:8} {row['Trades']:6d} {row['NetPnL_MXN']:10.2f} {row['GrossPnL_MXN']:12.2f} "
                  f"{row['TP_Rate']:>7} {row['SL_Rate']:>7} {row['H_Rate']:>7} "
                  f"{row['TP_pct']:>7} {row['SL_pct']:>7} {row['H_days']:6d} {row['CashPerTrade']:12.1f} "
                  f"{row['Notes']}")
        else:
            print(f"{m:8} {'-':>6} {'-':>10} {'-':>12} {'-':>7} {'-':>7} {'-':>7} {'-':>7} {'-':>7} {'-':>6} {'-':>12} "
                  f"{';'.join(notes)}")

    # Totales
    net_sum = sum(r["NetPnL_MXN"] for r in rows if r.get("NetPnL_MXN") is not None)
    print("\n---")
    print(f"Acumulado NetPnL (MXN): {net_sum:,.2f}")

    # Export CSV (opcional)
    if args.csv_out:
        import csv
        csv_path = Path(args.csv_out)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                w.writeheader()
                w.writerows(rows)
        print(f"[OK] CSV exportado → {csv_path}")

    # Exit code si hubo problemas
    if any_error:
        sys.exit(2)

if __name__ == "__main__":
    main()

