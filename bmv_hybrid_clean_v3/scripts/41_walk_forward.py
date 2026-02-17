# scripts/41_walk_forward.py
from __future__ import annotations
import argparse, subprocess, sys, json, os
from pathlib import Path
from datetime import datetime
import pandas as pd

def month_range(start_ym: str, end_ym: str) -> list[str]:
    y, m = map(int, start_ym.split("-")); start = datetime(y, m, 1)
    y2, m2 = map(int, end_ym.split("-")); end = datetime(y2, m2, 1)
    out = []
    cur_y, cur_m = y, m
    while (cur_y < y2) or (cur_y == y2 and cur_m <= m2):
        out.append(f"{cur_y:04d}-{cur_m:02d}")
        cur_m += 1
        if cur_m == 13:
            cur_m = 1; cur_y += 1
    return out

def last_n_months_up_to(target: str, n: int) -> list[str]:
    months = month_range("2000-01", target)  # dummy start
    months = months[:-1]  # excluye el target
    return months[-n:] if n > 0 else months

def build_train_months(mode: str, seed: list[str], target: str, slide_n: int) -> list[str]:
    if mode == "expanding":
        return [*seed, *month_range(seed[-1], target)][:-1] if seed else month_range("2000-01", target)[:-1]
    else:
        return last_n_months_up_to(target, slide_n)

def run_pipeline(train_months: list[str], forecast_month: str, args) -> int:
    base = [
        sys.executable if sys.executable else "python", "scripts/run_pipeline.py",
        "--months", *train_months,
        "--return-horizons", args.return_horizons,
        "--target-kind", args.target_kind,
        "--forecast-month", forecast_month,
        "--infer-h", str(args.infer_h),
        "--rank-topn", str(args.rank_topn),
        "--date-col", args.date_col,
        "--price-col", args.price_col,
        "--ticker-col", args.ticker_col,
        "--kpi-sizing", args.kpi_sizing,
        "--kpi-fixed-cash", str(args.kpi_fixed_cash),
        "--kpi-fixed-shares", str(args.kpi_fixed_shares),
        "--kpi-risk-pct", str(args.kpi_risk_pct),
        "--kpi-commission", str(args.kpi_commission),
    ]
    if args.collect_run: base += ["--collect-run"]
    if args.label: base += ["--label", args.label]
    if args.zip: base += ["--zip"]
    if args.include_models: base += ["--include-models"]
    if args.include_config: base += ["--include-config"]
    if args.min_prob is not None: base += ["--min-prob", str(args.min_prob)]
    if args.cfg: base += ["--cfg", args.cfg]

    print("\n>>> CMD:", " ".join(base))
    return subprocess.call(base)

def read_kpis_for_month(reports_dir: str, ym: str) -> dict:
    # Primero intenta kpi_mxn.json
    kpi_path = Path(reports_dir) / "forecast" / ym / "validation" / "kpi_mxn.json"
    if kpi_path.exists():
        try:
            return json.loads(kpi_path.read_text(encoding="utf-8")) | {"month": ym}
        except Exception:
            pass
    # Si no hay json, intenta leer validation_trades_auto.csv para KPIs básicos:
    trades_csv = Path(reports_dir) / "forecast" / ym / "validation" / "validation_trades_auto.csv"
    if trades_csv.exists():
        try:
            import numpy as np
            df = pd.read_csv(trades_csv)
            trades = len(df)
            winrate = float((df["pnl"] > 0).mean() * 100) if "pnl" in df.columns else None
            pnl_sum = float(df["pnl"].sum()) if "pnl" in df.columns else None
            return {"month": ym, "Trades": trades, "WinRate_%": winrate, "PnL_sum": pnl_sum}
        except Exception:
            pass
    return {"month": ym}

def main():
    ap = argparse.ArgumentParser(description="Walk-forward automático (expanding o sliding).")
    ap.add_argument("--targets-start", required=True, help="Primer mes a predecir, ej. 2025-01")
    ap.add_argument("--targets-end", required=True, help="Último mes a predecir, ej. 2025-09")
    ap.add_argument("--mode", choices=["expanding","sliding"], default="expanding")
    ap.add_argument("--slide-n", type=int, default=6, help="N meses para ventana fija (sliding)")
    ap.add_argument("--seed-start", help="Inicio de semilla (expanding), ej. 2024-01")
    ap.add_argument("--seed-end", help="Fin de semilla (expanding), ej. 2024-12")

    # Hiperparámetros del pipeline
    ap.add_argument("--return-horizons", default="3", help="Ej. 3,5,10")
    ap.add_argument("--target-kind", choices=["raw","volnorm"], default="raw")
    ap.add_argument("--infer-h", type=int, default=3)
    ap.add_argument("--rank-topn", type=int, default=20)
    ap.add_argument("--date-col", default="entry_date")
    ap.add_argument("--price-col", default="entry_price")
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--min-prob", type=float, default=0.0)

    # KPI MXN
    ap.add_argument("--kpi-sizing", choices=["fixed_shares","fixed_cash","percent_risk"], default="fixed_cash")
    ap.add_argument("--kpi-fixed-cash", type=float, default=10000.0)
    ap.add_argument("--kpi-fixed-shares", type=int, default=100)
    ap.add_argument("--kpi-risk-pct", type=float, default=0.02)
    ap.add_argument("--kpi-commission", type=float, default=5.0)

    # Packaging
    ap.add_argument("--collect-run", action="store_true")
    ap.add_argument("--label", default="wf")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--include-models", action="store_true")
    ap.add_argument("--include-config", action="store_true")
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--reports-dir", default="reports")
    ap.add_argument("--summary-out", default="reports/wf_summary.csv")
    args = ap.parse_args()

    # Construye semilla para expanding
    seed = []
    if args.mode == "expanding":
        if not args.seed_start or not args.seed_end:
            ap.error("Para mode=expanding necesitas --seed-start y --seed-end")
        seed = month_range(args.seed_start, args.seed_end)

    targets = month_range(args.targets_start, args.targets_end)
    all_rows = []

    for ym in targets:
        train_months = build_train_months(args.mode, seed, ym, args.slide_n)
        if not train_months:
            print(f"⚠️ Sin meses de entrenamiento para target {ym}, salto.")
            continue
        print(f"\n==== Target {ym} | Train months ({len(train_months)}): {train_months[:3]} ... {train_months[-3:]}")
        rc = run_pipeline(train_months, ym, args)
        if rc != 0:
            print(f"❌ Pipeline falló para {ym} (rc={rc}). Sigo con el siguiente…")
        # leer KPIs
        k = read_kpis_for_month(args.reports_dir, ym)
        all_rows.append(k)

        # en expanding, añade el target recién predicho al set de entrenamiento (opcional)
        if args.mode == "expanding":
            if ym not in seed:
                seed.append(ym)

    # Guardar resumen
    if all_rows:
        df = pd.DataFrame(all_rows)
        Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.summary_out, index=False, encoding="utf-8")
        print(f"\n✅ Resumen guardado en {args.summary_out}")
        print(df.fillna("").to_string(index=False))
    else:
        print("\n⚠️ No se generó ningún resumen (no hubo KPIs).")

if __name__ == "__main__":
    main()
