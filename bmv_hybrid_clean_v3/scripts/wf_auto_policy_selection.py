# scripts/wf_auto_policy_selection.py
from __future__ import annotations
import argparse, csv, json, os, sys, subprocess, shlex
from pathlib import Path
from typing import List, Tuple
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]  # asumiendo scripts/ dentro del repo

def parse_grid_list(raw: List[str]) -> List[str]:
    """
    Acepta múltiples banderas y/o listas separadas por coma.
    Ej: ["0.05,0.06","0.07"] -> ["0.05","0.06","0.07"]
    """
    vals: List[str] = []
    for item in raw:
        for piece in str(item).split(","):
            piece = piece.strip()
            if piece:
                vals.append(piece)
    return vals

def run(cmd: List[str], cwd: Path | None = None, env_extra: dict | None = None) -> int:
    env = os.environ.copy()
    # Asegura PYTHONPATH al repo
    env["PYTHONPATH"] = str(REPO_ROOT)
    if env_extra:
        env.update(env_extra)
    print(f"▶ {shlex.join(cmd)}")
    rc = subprocess.run(cmd, cwd=str(cwd or REPO_ROOT)).returncode
    if rc != 0:
        print(f"✗ return code {rc} for: {cmd}", file=sys.stderr)
    return rc

def ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def write_json_utf8_no_bom(path: Path, obj: dict):
    ensure_dir(path)
    data = json.dumps(obj, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)

def forecast_and_validate(py: str, month: str) -> Tuple[bool, Path]:
    """Corre 12_forecast_and_validate.py y devuelve (ok, validation_dir)."""
    rc = run([py, "scripts/12_forecast_and_validate.py", "--month", month])
    val_dir = REPO_ROOT / f"reports/forecast/{month}/validation"
    csv_auto = val_dir / "validation_join_auto.csv"
    ok = rc == 0 and csv_auto.exists()
    return ok, val_dir

def apply_open_limits(py: str, csv_in: Path, month: str, per_trade_cash: int, max_open: int, budget: int) -> Path | None:
    out_csv = REPO_ROOT / f"runs/{month}_validation_join_auto_limited.csv"
    ensure_dir(out_csv)
    dec_log = REPO_ROOT / f"runs/open_decisions_{month}.csv"
    rc = run([
        py, "scripts/27_filter_open_limits.py",
        "--in", str(csv_in),
        "--out", str(out_csv),
        "--decision-log", str(dec_log),
        "--max-open", str(max_open),
        "--per-trade-cash", str(per_trade_cash),
        "--budget", str(budget),
    ])
    return out_csv if rc == 0 and out_csv.exists() else None

def gridsearch_policy(
    py: str,
    month: str,
    validation_dir: Path,
    csv_for_policy: Path,
    grid_tp: List[str],
    grid_sl: List[str],
    grid_h: List[str],
    min_abs_y: float,
    per_trade_cash: int,
) -> Path | None:
    out_dir = REPO_ROOT / f"runs/{month}_grid"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = out_dir / "grid_summary.csv"

    args = [
        py, "scripts/27_policy_gridsearch.py",
        "--month", month,
        "--grid-tp", ",".join(grid_tp),
        "--grid-sl", ",".join(grid_sl),
        "--grid-h", ",".join(grid_h),
        "--min-abs-y", str(min_abs_y),
        "--per-trade-cash", str(per_trade_cash),
        "--summary-out", str(summary_csv),
        "--validation-dir", str(validation_dir),
        "--out-dir", str(out_dir),
    ]

    # Si estamos usando el CSV limitado, pedir modo inline y pasar el CSV explícito
    default_csv = validation_dir / "validation_join_auto.csv"
    if csv_for_policy.resolve() != default_csv.resolve():
        args += ["--use-inline", "--csv-in", str(csv_for_policy)]

    rc = run(args)
    return summary_csv if rc == 0 and summary_csv.exists() else None

def pick_best_from_summary(summary_csv: Path) -> Tuple[float,float,int,pd.Series] | None:
    df = pd.read_csv(summary_csv)
    if df.empty:
        return None
    df = df.sort_values("net_pnl_sum", ascending=False)
    best = df.iloc[0]
    return float(best["tp_pct"]), float(best["sl_pct"]), int(best["horizon_days"]), best

def recompute_with_policy(
    py: str,
    month: str,
    validation_dir: Path,
    csv_in: Path,
    tp: float,
    sl: float,
    h: int,
    min_abs_y: float,
    per_trade_cash: int,
) -> Path | None:
    pol_json = REPO_ROOT / f"runs/policy_best_{month}.json"
    write_json_utf8_no_bom(pol_json, {
        "month": month,
        "tp_pct": tp,
        "sl_pct": sl,
        "horizon_days": h,
        "min_abs_y": min_abs_y,
        "long_only": True,
        "per_trade_cash": per_trade_cash,
        "commission_side": 5.0,
    })
    out_trades = REPO_ROOT / f"runs/{month}_validation_trades_policy_best.csv"
    kpi_out = REPO_ROOT / f"runs/kpi_policy_best_{month}.json"
    rc = run([
        py, "scripts/26_policy_recompute_pnl.py",
        "--month", month,
        "--policy-json", str(pol_json),
        "--validation-dir", str(validation_dir),
        "--csv-in", str(csv_in),
        "--csv-out", str(out_trades),
        "--kpi-json-out", str(kpi_out),
    ])
    return kpi_out if rc == 0 and kpi_out.exists() else None

def append_summary(summary_out: Path, kpi_json: Path, csv_source: Path):
    with open(kpi_json, "r", encoding="utf-8") as f:
        k = json.load(f)
    row = {
        "Month": k.get("month"),
        "Trades": k.get("trades"),
        "net_pnl_sum": round(float(k.get("net_pnl_sum", 0.0)), 2),
        "gross_pnl_sum": round(float(k.get("gross_pnl_sum", 0.0)), 2),
        "tp_rate": k.get("tp_rate"),
        "sl_rate": k.get("sl_rate"),
        "horizon_rate": k.get("horizon_rate"),
        "tp_pct": k.get("tp_pct"),
        "sl_pct": k.get("sl_pct"),
        "horizon_days": k.get("horizon_days"),
        "per_trade_cash": k.get("per_trade_cash"),
        "source_csv": str(csv_source),
    }
    new_file = not summary_out.exists()
    ensure_dir(summary_out)
    with open(summary_out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)

def main():
    ap = argparse.ArgumentParser(
        description="WF auto policy selection (Python-only): forecast→validate→(optional) open-limits → gridsearch TP/SL/H → apply best → consolidate KPIs."
    )
    ap.add_argument("--months", nargs="+", required=True, help="Meses YYYY-MM (uno o varios)")
    ap.add_argument("--grid-tp", nargs="+", default=["0.05","0.06","0.07"])
    ap.add_argument("--grid-sl", nargs="+", default=["0.01","0.015","0.02"])
    ap.add_argument("--grid-h",  nargs="+", default=["3","4","5"])
    ap.add_argument("--min-abs-y", type=float, default=0.06)
    ap.add_argument("--per-trade-cash", type=int, default=2500)
    ap.add_argument("--max-open", type=int, default=5)
    ap.add_argument("--budget", type=int, default=10000)
    ap.add_argument("--use-open-limits", action="store_true", help="Aplica 27_filter_open_limits antes de gridsearch")
    ap.add_argument("--summary-out", default="runs/wf_auto_summary.csv")
    ap.add_argument("--python-bin", default=str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
                    help="Ruta a Python (default .venv). Si no existe, usará 'python' del PATH.")
    args = ap.parse_args()

    py = args.python_bin if Path(args.python_bin).exists() else "python"
    grid_tp = parse_grid_list(args["grid_tp"] if isinstance(args, dict) else args.grid_tp)
    grid_sl = parse_grid_list(args["grid_sl"] if isinstance(args, dict) else args.grid_sl)
    grid_h  = parse_grid_list(args["grid_h"]  if isinstance(args, dict) else args.grid_h)

    summary_out = REPO_ROOT / args.summary_out
    ensure_dir(summary_out)

    for month in args.months:
        print("\n" + "="*12 + f" {month} " + "="*12)
        ok, val_dir = forecast_and_validate(py, month)
        if not ok:
            print(f"⚠️  Forecast/validate falló o falta validation_join_auto.csv para {month}", file=sys.stderr)
            continue

        csv_auto = val_dir / "validation_join_auto.csv"
        csv_for_policy = csv_auto

        if args.use_open_limits:
            print(f"ℹ️  Aplicando open-limits (per_trade_cash={args.per_trade_cash}, max_open={args.max_open}, budget={args.budget})")
            limited = apply_open_limits(py, csv_auto, month, args.per_trade_cash, args.max_open, args.budget)
            if limited is None:
                print(f"⚠️  No se pudo limitar open-limits, sigo con validation_join_auto.csv", file=sys.stderr)
            else:
                csv_for_policy = limited

        summary_csv = gridsearch_policy(
            py=py,
            month=month,
            validation_dir=val_dir,
            csv_for_policy=csv_for_policy,
            grid_tp=grid_tp,
            grid_sl=grid_sl,
            grid_h=grid_h,
            min_abs_y=args.min_abs_y,
            per_trade_cash=args.per_trade_cash,
        )
        if summary_csv is None:
            print(f"⚠️  Gridsearch falló para {month}", file=sys.stderr)
            continue

        pick = pick_best_from_summary(summary_csv)
        if not pick:
            print(f"⚠️  Grid vacío para {month}", file=sys.stderr)
            continue
        best_tp, best_sl, best_h, row = pick
        print(f"✅ Mejor {month}: TP={best_tp:.3%}  SL={best_sl:.3%}  H={best_h}  ⇒ NetPnL={row['net_pnl_sum']:.2f}")

        kpi_json = recompute_with_policy(
            py=py,
            month=month,
            validation_dir=val_dir,
            csv_in=csv_for_policy,
            tp=best_tp,
            sl=best_sl,
            h=best_h,
            min_abs_y=args.min_abs_y,
            per_trade_cash=args.per_trade_cash,
        )
        if not kpi_json:
            print(f"⚠️  Recompute con mejor política falló ({month})", file=sys.stderr)
            continue

        append_summary(summary_out, kpi_json, csv_for_policy)

    # Mostrar resumen ordenado
    if summary_out.exists():
        print("\n===== Resumen por NetPnL (desc) =====")
        df = pd.read_csv(summary_out)
        if not df.empty:
            df_sorted = df.sort_values("net_pnl_sum", ascending=False).copy()
            # formatea tasas si existen
            for col in ["tp_rate", "sl_rate", "horizon_rate", "tp_pct", "sl_pct"]:
                if col in df_sorted.columns:
                    df_sorted[col] = (df_sorted[col]*100).round(1).astype(str) + "%"
            print(df_sorted[[
                "Month","Trades","net_pnl_sum","gross_pnl_sum",
                "tp_rate","sl_rate","horizon_rate",
                "tp_pct","sl_pct","horizon_days","per_trade_cash"
            ]].to_string(index=False))
            total = float(df["net_pnl_sum"].sum())
            print(f"\n🧮 Acumulado NetPnL (MXN): {total:,.2f}")
        else:
            print("No hay filas en el resumen.")
    else:
        print("No se generó resumen.")

if __name__ == "__main__":
    main()
