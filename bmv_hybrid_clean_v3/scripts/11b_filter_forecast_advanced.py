# scripts/11b_filter_forecast_advanced.py
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

def parse_args():
    ap = argparse.ArgumentParser(
        description="Filtra señales por presupuesto diario y sizing fijo por trade; ordena por EV y/o probabilidad."
    )
    ap.add_argument("--in-csv", required=True, help="CSV de entrada (de 12_... con EV). Debe incluir al menos date,ticker,side")
    ap.add_argument("--out-csv", required=True, help="CSV de salida filtrado")
    ap.add_argument("--daily-budget-mxn", type=float, required=True, help="Presupuesto diario total (MXN)")
    ap.add_argument("--per-trade-cash", type=float, required=True, help="Efectivo fijo por trade (MXN)")
    ap.add_argument("--daily-topn", type=int, default=5, help="Máximo de señales por día (default: 5)")

    # Orden/selección
    ap.add_argument("--sort-by",
                    choices=["expected_value", "prob_first", "ev_then_prob"],
                    default="expected_value",
                    help="Estrategia de orden: EV puro | prob luego EV | EV luego prob (default: expected_value)")
    ap.add_argument("--ascending", action="store_true",
                    help="Orden ascendente (por default es descendente para métricas ‘mejor es mayor’)")

    # Prob/EV flexibles
    ap.add_argument("--prob_col", default="prob_win",
                    help="Columna de probabilidad a usar (default: prob_win)")
    ap.add_argument("--min-prob", type=float, default=None,
                    help="Descarta señales con prob < umbral (opcional)")
    ap.add_argument("--min-ev", type=float, default=None,
                    help="Descarta señales con EV < umbral (opcional)")

    return ap.parse_args()

def coerce_side(s):
    if pd.isna(s):
        return np.nan
    s = str(s).strip().upper()
    if s in ("BUY", "LONG", "L"):  return "BUY"
    if s in ("SELL", "SHORT", "S"): return "SELL"
    return s

def main():
    args = parse_args()

    in_path  = Path(args.in_csv)
    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        raise SystemExit(f"❌ No encontré input: {in_path}")

    df = pd.read_csv(in_path)
    if df.empty:
        raise SystemExit("❌ El CSV de entrada está vacío.")

    # Columnas mínimas
    needed = ["date", "ticker", "side"]
    miss = [c for c in needed if c not in df.columns]
    if miss:
        raise SystemExit(f"❌ Faltan columnas requeridas: {miss}")

    # Parseo/normalización
    df["date"]   = pd.to_datetime(df["date"], errors="coerce")
    df           = df.dropna(subset=["date"]).copy()
    df["ticker"] = df["ticker"].astype(str)
    df["side"]   = df["side"].map(coerce_side)

    # Columnas de métricas
    ev_col   = "expected_value"
    prob_col = args.prob_col

    # Si faltan, créalas “suave”
    if ev_col not in df.columns:
        df[ev_col] = 0.0
        print(f"⚠️ No encontré '{ev_col}' en input; se rellenó con 0.0 (revisa que corrió el script de EV).")
    if prob_col not in df.columns:
        df[prob_col] = 0.0
        print(f"⚠️ No encontré columna de prob '{prob_col}'; seguiré sin filtrar por probabilidad.")

    # Numéricos y clamps
    df[ev_col]   = pd.to_numeric(df[ev_col], errors="coerce").fillna(0.0)
    df[prob_col] = pd.to_numeric(df[prob_col], errors="coerce").fillna(0.0)
    if prob_col.lower().startswith("prob"):
        df[prob_col] = df[prob_col].clip(0, 1)

    # Filtros opcionales
    if args.min_prob is not None and prob_col in df.columns:
        b = len(df); df = df[df[prob_col] >= args.min_prob]; a = len(df)
        print(f"• Filtro min_prob={args.min_prob:.2f} → {b} → {a} filas")
    if args.min_ev is not None:
        b = len(df); df = df[df[ev_col] >= args.min_ev]; a = len(df)
        print(f"• Filtro  min_ev={args.min_ev:.4f} → {b} → {a} filas")

    # Orden
    asc = args.ascending
    if args.sort_by == "expected_value":
        sort_cols = [ev_col]
        asc_list  = [asc]
    elif args.sort_by == "prob_first":
        sort_cols = [prob_col, ev_col]
        asc_list  = [asc, asc]
    else:  # "ev_then_prob"
        sort_cols = [ev_col, prob_col]
        asc_list  = [asc, asc]

    # Orden total pero preserva agrupación diaria
    df = df.sort_values(["date"] + sort_cols, ascending=[True] + asc_list).copy()

    # Cupo por presupuesto
    if args.per_trade_cash <= 0 or args.daily_budget_mxn <= 0:
        raise SystemExit("❌ per-trade-cash y daily-budget-mxn deben ser > 0.")
    budget_cap = int(np.floor(args.daily_budget_mxn / args.per_trade_cash))
    if budget_cap <= 0:
        raise SystemExit("❌ El presupuesto diario no alcanza para 1 trade con el per-trade-cash dado.")

    per_day_limit = int(min(budget_cap, max(1, args.daily_topn)))

    # Selección por día
    out_rows = []
    for day, g in df.groupby(df["date"].dt.normalize()):
        g2 = g.head(per_day_limit).copy()
        g2["cash_size_mxn"] = float(args.per_trade_cash)
        out_rows.append(g2)

    out_df = pd.concat(out_rows, axis=0) if out_rows else pd.DataFrame(columns=df.columns)
    out_df = out_df.sort_values(["date"] + sort_cols, ascending=[True] + asc_list)

    # Guardar
    out_df.to_csv(out_path, index=False, encoding="utf-8")
    used_prob = prob_col if prob_col in df.columns else "(none)"
    print(f"✅ Filtrado diario listo → {out_path}")
    print("   Reglas: "
          f"budget=${args.daily_budget_mxn:,.2f} | per_trade=${args.per_trade_cash:,.2f} | "
          f"topN={args.daily_topn} | sort={args.sort_by} | prob={used_prob}")

if __name__ == "__main__":
    main()
