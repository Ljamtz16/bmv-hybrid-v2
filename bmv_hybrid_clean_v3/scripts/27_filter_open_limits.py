# scripts/27_filter_open_limits.py
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
# Import local desde el mismo directorio "scripts"
from utils_limited_open import select_signals_with_limits


def main():
    ap = argparse.ArgumentParser(description="Filtra validation_join_auto.csv aplicando tope de simultaneidad/presupuesto por día (entradas).")
    ap.add_argument("--in", dest="src", required=True, help="validation_join_auto.csv")
    ap.add_argument("--out", dest="dst", required=True, help="validation_join_auto_limited.csv")
    ap.add_argument("--max-open", type=int, default=0, help="Máximo de posiciones nuevas por día (aprox). 0 = sin tope por conteo.")
    ap.add_argument("--per-trade-cash", type=float, default=0.0, help="Capital por operación.")
    ap.add_argument("--budget", type=float, default=0.0, help="Presupuesto diario para nuevas entradas. 0 = sin tope por presupuesto.")
    ap.add_argument("--decision-log", default="", help="CSV para auditar decisiones OPEN/SKIP.")
    args = ap.parse_args()

    src = Path(args.src); dst = Path(args.dst)
    df = pd.read_csv(src)

    if "date" not in df.columns:
        raise SystemExit("El CSV debe tener columna 'date' (YYYY-MM-DD).")

    # Normaliza columnas prob/ev si existen
    if "prob" not in df.columns and "prob_win" in df.columns:
        df["prob"] = df["prob_win"]
    if "ev" not in df.columns and "expected_value" in df.columns:
        df["ev"] = df["expected_value"]

    out_rows = []
    for day, dfi in df.groupby("date", sort=True):
        # por simplicidad, tratamos el límite como tope de ENTRADAS por día
        signals_today = dfi.to_dict("records")
        selected = select_signals_with_limits(
            signals_today=signals_today,
            open_positions_count=0,               # si quieres llevar conteo multi-día real, necesitas entry/exit y memoria
            max_open=(args.max_open if args.max_open>0 else None),
            per_trade_cash=(args.per_trade_cash if args.per_trade_cash>0 else None),
            budget=(args.budget if args.budget>0 else None),
            decision_log_csv=(args.decision_log if args.decision_log else None),
            now_dt=datetime.fromisoformat(str(day)) if isinstance(day,str) else day,
        )
        if selected:
            out_rows.extend(selected)

    out = pd.DataFrame(out_rows) if out_rows else df.iloc[0:0].copy()
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dst, index=False)
    print(f"✅ Guardado: {dst}  (filas: {len(out)})")

if __name__ == "__main__":
    main()
