#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse, os, sys, json, hashlib, subprocess
import pandas as pd
from datetime import datetime

# === Rutas robustas (sin "scripts/scripts/..." duplicado) ===
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.normpath(os.path.join(SCRIPTS_DIR, ".."))
PYTHON_EXE  = sys.executable  # usa el intérprete actual (tu venv)

RECOMPUTE_PY  = os.path.join(SCRIPTS_DIR, "26_policy_recompute_pnl.py")
OPENLIMITS_PY = os.path.join(SCRIPTS_DIR, "27_filter_open_limits.py")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def date_span_ok(df, month):
    """Verifica que las fechas del CSV estén dentro del mes dado (YYYY-MM)."""
    dmin = pd.to_datetime(df["date"].min()).date()
    dmax = pd.to_datetime(df["date"].max()).date()
    start = datetime.strptime(month + "-01", "%Y-%m-%d").date()
    # fin de mes (primer día del mes siguiente)
    if start.month == 12:
        end = datetime(start.year + 1, 1, 1).date()
    else:
        end = datetime(start.year, start.month + 1, 1).date()
    end = end.replace(day=1)
    return dmin >= start and dmax < end, dmin, dmax

def run(cmd_args):
    # Helper para imprimir y ejecutar
    print("▶", PYTHON_EXE, *cmd_args)
    r = subprocess.run([PYTHON_EXE, *cmd_args], capture_output=True, text=True)
    if r.stdout:
        print(r.stdout, end="")
    if r.stderr:
        print(r.stderr, end="")
    return r.returncode

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)  # YYYY-MM
    ap.add_argument("--best-policy-json", required=True)
    ap.add_argument("--limited-csv", required=True)
    ap.add_argument("--per-trade-cash", type=float, default=2000.0)
    ap.add_argument("--max-open", type=int, default=5)
    ap.add_argument("--budget", type=float, default=10000.0)
    ap.add_argument("--long-only", action="store_true",
                    help="Si se usa, fuerza evaluar sólo señales BUY en recompute (base/vecinos/WF).")
    args = ap.parse_args()

    month = args.month
    best_json = os.path.abspath(args.best_policy_json)
    limited_csv = os.path.abspath(args.limited_csv)

    # Validación preliminar
    if not os.path.exists(best_json):
        print(f"⚠️  No encontré {best_json}, continuaré pero no podré comparar contra el KPI original de la grid.")

    if not os.path.exists(limited_csv):
        print(f"[ERROR] No existe CSV limitado: {limited_csv}")
        sys.exit(2)

    # 1) Reproducibilidad
    print("\n=== 1) Reproducibilidad ===")
    if args.long_only:
        print("   (modo: LONG-ONLY activo — sólo BUY)")

    df = pd.read_csv(limited_csv)
    file_hash = sha256_file(limited_csv)
    ok_span, dmin, dmax = date_span_ok(df, month)
    print("CSV:", limited_csv)
    print(f"  filas={len(df)}  sha256={file_hash}")
    print(f"  fechas: [{dmin} .. {dmax}]  dentro_del_mes={ok_span}")

    # recompute con 26_policy_recompute_pnl.py
    validation_dir = os.path.join(ROOT_DIR, "reports", "forecast", month, "validation")
    out_recheck_trades = os.path.join(SCRIPTS_DIR, "runs", "audit_rechecks", f"{month}_recheck_trades.csv")
    out_recheck_kpi    = os.path.join(SCRIPTS_DIR, "runs", "audit_rechecks", f"{month}_recheck_kpi.json")
    os.makedirs(os.path.dirname(out_recheck_trades), exist_ok=True)

    recompute_cmd = [
        RECOMPUTE_PY,
        "--month", month,
        "--policy-json", best_json,
        "--validation-dir", validation_dir,
        "--csv-in", limited_csv,
        "--csv-out", out_recheck_trades,
        "--kpi-json-out", out_recheck_kpi
    ]
    if args.long_only:
        recompute_cmd.append("--long-only")

    rc = run(recompute_cmd)
    if rc != 0:
        print("ERROR recompute KPI (recheck)")
        sys.exit(3)

    try:
        kpi = json.load(open(out_recheck_kpi, "r", encoding="utf-8"))
        print(f"Recompute net_pnl_sum: {kpi.get('net_pnl_sum')}  trades={kpi.get('trades')}")
    except Exception as e:
        print("[ERROR] No pude leer KPI recheck:", e)
        sys.exit(4)

    # 2) Robustez (vecindad del óptimo)
    print("\n=== 2) Robustez (vecindad del óptimo) ===")
    base = json.load(open(best_json, "r", encoding="utf-8"))
    tp = float(base["tp_pct"]); sl = float(base["sl_pct"]); h = int(base["horizon_days"])

    d_tp = [tp-0.01, tp, tp+0.01]                     # ±1 pp
    d_sl = [max(sl/2, sl-0.0005), sl, sl+0.0005]      # leve variación
    d_h  = [h-1, h, h+1]

    combos = []
    for t in d_tp:
        for s in d_sl:
            for hh in d_h:
                if hh < 1:
                    continue
                neighbor = dict(base)
                neighbor["tp_pct"] = round(t, 4)
                neighbor["sl_pct"] = round(s, 4)
                neighbor["horizon_days"] = int(hh)
                combos.append(neighbor)

    results = []
    neighbor_dir = os.path.join(SCRIPTS_DIR, "runs", "audit_neighbors")
    os.makedirs(neighbor_dir, exist_ok=True)

    for nb in combos:
        tag = f"tp{nb['tp_pct']:.4f}_sl{nb['sl_pct']:.4f}_h{nb['horizon_days']}"
        nb_json = os.path.join(neighbor_dir, f"policy_neighbor_{tag}.json")
        with open(nb_json, "w", encoding="utf-8") as f:
            json.dump(nb, f, ensure_ascii=False, indent=2)

        out_trades = os.path.join(neighbor_dir, f"{month}_neighbor_{tag}_trades.csv")
        out_kpi    = os.path.join(neighbor_dir, f"{month}_neighbor_{tag}_kpi.json")

        nb_cmd = [
            RECOMPUTE_PY,
            "--month", month,
            "--policy-json", nb_json,
            "--validation-dir", validation_dir,
            "--csv-in", limited_csv,
            "--csv-out", out_trades,
            "--kpi-json-out", out_kpi
        ]
        if args.long_only:
            nb_cmd.append("--long-only")

        rc = run(nb_cmd)
        if rc == 0:
            try:
                kk = json.load(open(out_kpi, "r", encoding="utf-8"))
                results.append((nb["tp_pct"], nb["sl_pct"], nb["horizon_days"], kk.get("net_pnl_sum", float("nan"))))
            except Exception:
                pass

    results = sorted(results, key=lambda x: x[3], reverse=True)
    print(f"Vecindad: {len(results)} combinaciones")
    if results:
        print("Top-5 vecinos por NetPnL:")
        for row in results[:5]:
            print(f"  TP={row[0]*100:.2f}% SL={row[1]*100:.2f}% H={row[2]} → {row[3]:.2f}")
        print("Peores-3 vecinos por NetPnL:")
        for row in results[-3:]:
            print(f"  TP={row[0]*100:.2f}% SL={row[1]*100:.2f}% H={row[2]} → {row[3]:.2f}")
        mediana = float(pd.Series([r[3] for r in results]).median())
        print(f"Mediana vecinos: {mediana:.2f}  | Óptimo base(recheck): {kpi.get('net_pnl_sum'):.2f}")

    # 3) Walk-forward (aplicar política del mes al siguiente)
    print("\n=== 3) Walk-forward (aplicar política del mes a siguiente) ===")
    dt = datetime.strptime(month + "-01", "%Y-%m-%d")
    next_month = f"{dt.year+1}-01" if dt.month == 12 else f"{dt.year:04d}-{dt.month+1:02d}"

    next_validation = os.path.join(ROOT_DIR, "reports", "forecast", next_month, "validation", "validation_join_auto.csv")
    if not os.path.exists(next_validation):
        print(f"⚠️  No existe validación de {next_month}: {next_validation}")
        print("WF se omite.")
    else:
        limited_next = os.path.join(SCRIPTS_DIR, "runs", f"{next_month}_validation_join_auto_limited_from_{month}.csv")
        os.makedirs(os.path.dirname(limited_next), exist_ok=True)

        rc = run([
            OPENLIMITS_PY,
            "--in", next_validation,
            "--out", limited_next,
            "--decision-log", os.path.join(SCRIPTS_DIR, "runs", f"open_decisions_{next_month}_from_{month}.csv"),
            "--max-open", str(args.max_open),
            "--per-trade-cash", str(args.per_trade_cash),
            "--budget", str(args.budget)
        ])
        if rc == 0:
            out_wf_trades = os.path.join(SCRIPTS_DIR, "runs", "audit_wf", f"{next_month}_wf_from_{month}_trades.csv")
            out_wf_kpi    = os.path.join(SCRIPTS_DIR, "runs", "audit_wf", f"{next_month}_wf_from_{month}_kpi.json")
            os.makedirs(os.path.dirname(out_wf_trades), exist_ok=True)

            wf_cmd = [
                RECOMPUTE_PY,
                "--month", next_month,
                "--policy-json", best_json,
                "--validation-dir", os.path.join(ROOT_DIR, "reports", "forecast", next_month, "validation"),
                "--csv-in", limited_next,
                "--csv-out", out_wf_trades,
                "--kpi-json-out", out_wf_kpi
            ]
            if args.long_only:
                wf_cmd.append("--long-only")

            rc2 = run(wf_cmd)
            if rc2 == 0:
                kpi_wf = json.load(open(out_wf_kpi, "r", encoding="utf-8"))
                print(f"Walk-forward → {next_month}: net_pnl_sum={kpi_wf.get('net_pnl_sum')}, trades={kpi_wf.get('trades')}, "
                      f"tp_rate={kpi_wf.get('tp_rate')}, sl_rate={kpi_wf.get('sl_rate')}, h_rate={kpi_wf.get('horizon_rate')}")
                print("WF CSV:", limited_next)

    print("\n================ INFORME =================")
    print(f"CSV limitado filas={len(df)}, sha256={file_hash}")
    print(f"Recompute KPI (base): net_pnl_sum={kpi.get('net_pnl_sum')}, trades={kpi.get('trades')}")
    if results:
        mediana = float(pd.Series([r[3] for r in results]).median())
        print(f"\nRobustez (vecindad):\n  Óptimo(base)={kpi.get('net_pnl_sum'):.2f} | Mediana={mediana:.2f} | Top={results[0][3]:.2f} | Worst={results[-1][3]:.2f}")

    print("\nSugerencia de interpretación:")
    print("Considera el resultado válido si (a) el recompute coincide razonablemente con el ranking y las fechas")
    print("están dentro del mes (sin look-ahead), y (b) la mediana de la vecindad no se desploma respecto al óptimo.")
    print("El walk-forward añade evidencia out-of-sample.")

if __name__ == "__main__":
    main()
