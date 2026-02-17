# scripts/11_filter_forecast_daily_budget.py
import argparse, pandas as pd, numpy as np

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--in-csv", required=True, help="CSV de señales (e.g. latest_forecast_with_returns.csv)")
    p.add_argument("--out-csv", required=True, help="CSV filtrado de salida")
    p.add_argument("--daily-budget-mxn", type=float, required=True, help="Presupuesto máximo por día en MXN")
    p.add_argument("--per-trade-cash", type=float, required=True, help="Monto fijo por trade en MXN (p.ej. 1000)")
    p.add_argument("--sort-by", choices=["expected_value","prob"], default="expected_value")
    p.add_argument("--daily-topn", type=int, default=0, help="Máximo de señales por día (0=sin tope)")
    return p.parse_args()

def main():
    a = parse_args()
    df = pd.read_csv(a.in_csv)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    else:
        raise SystemExit("❌ Falta columna 'date' en el CSV de entrada.")

    sort_col = a.sort_by
    if sort_col not in df.columns:
        # permitir alias mínimos
        if sort_col == "expected_value" and "EV" in df.columns:
            sort_col = "EV"
        elif sort_col == "prob" and "prob_win" in df.columns:
            sort_col = "prob_win"
        elif sort_col not in df.columns:
            raise SystemExit(f"❌ No encuentro columna para ordenar: {a.sort_by}")

    out_rows = []
    for day, g in df.groupby("date"):
        g2 = g.sort_values(sort_col, ascending=False).copy()

        used = 0.0
        kept = []
        for i, r in g2.iterrows():
            if a.daily_topn and len(kept) >= a.daily_topn:
                break
            if used + a.per_trade_cash <= a.daily_budget_mxn + 1e-9:
                kept.append(r)
                used += a.per_trade_cash
            else:
                break

        if kept:
            out_rows.extend(kept)

    out = pd.DataFrame(out_rows)
    out.to_csv(a.out_csv, index=False, encoding="utf-8")
    print(f"✅ Filtrado diario listo → {a.out_csv}")
    print(f"   Reglas: budget=${a.daily_budget_mxn:,.2f} | per_trade=${a.per_trade_cash:,.2f} | topN={0 if a.daily_topn==0 else a.daily_topn} | sort={a.sort_by}")

if __name__ == "__main__":
    main()
