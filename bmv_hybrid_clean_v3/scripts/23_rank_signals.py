# scripts/23_rank_signals.py
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np

EV_ALIASES = ["expected_value", "ev", "EV"]
PROB_ALIASES = ["prob_win", "prob", "p_win"]
PREDRET_ALIASES = ["pred_return", "pred_return_5d", "pred_ret", "pred"]

def pick_col(df: pd.DataFrame, names: list[str]) -> str | None:
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        if n.lower() in low:
            return low[n.lower()]
    return None

def ensure_ev(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Devuelve (df_con_ev, ev_col). Si no existe EV, lo calcula con prob_win * pred_return."""
    ev_col = pick_col(df, EV_ALIASES)
    if ev_col:
        return df, ev_col

    prob_col = pick_col(df, PROB_ALIASES)
    ret_col  = pick_col(df, PREDRET_ALIASES)
    if not prob_col or not ret_col:
        raise SystemExit(
            "❌ No encontré columna de expected value ni pares suficientes para calcularla.\n"
            f"   Busqué EV en {EV_ALIASES}\n"
            f"   Busqué prob en {PROB_ALIASES}\n"
            f"   Busqué pred_return en {PREDRET_ALIASES}"
        )
    df = df.copy()
    df["__computed_ev__"] = pd.to_numeric(df[prob_col], errors="coerce") * pd.to_numeric(df[ret_col], errors="coerce")
    return df, "__computed_ev__"

def main():
    ap = argparse.ArgumentParser(description="Rankea señales por expected value y exporta TOP-N.")
    ap.add_argument("--in_csv", required=True, help="CSV con pred_return y expected_value (o prob*pred_return).")
    ap.add_argument("--out", default="reports/forecast/ranked_signals_topN.csv", help="CSV de salida con el TOP-N.")
    ap.add_argument("--top_n", type=int, default=20, help="N de señales a exportar (0 = todas ordenadas).")
    ap.add_argument("--min_prob", type=float, default=0.0, help="Filtro mínimo de prob_win (si existe).")
    ap.add_argument("--per_ticker", type=int, default=0, help="Máximo de señales por ticker (0 = sin límite).")
    ap.add_argument("--meta_out", default="reports/forecast/ranked_signals_meta.json", help="JSON con metadatos del ranking.")
    args = ap.parse_args()

    df = pd.read_csv(args.in_csv)
    if df.empty:
        raise SystemExit("❌ El CSV de entrada está vacío.")

    # Normaliza columnas clave comunes si existen
    for c in ["date", "entry_date"]:
        if c in df.columns:
            try:
                df[c] = pd.to_datetime(df[c], errors="coerce")
            except Exception:
                pass
    for c in ["ticker", "side"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.upper().str.strip()

    # Filtra por prob mínima si hay columna de prob
    prob_col = pick_col(df, PROB_ALIASES)
    if prob_col and args.min_prob > 0:
        df = df[pd.to_numeric(df[prob_col], errors="coerce") >= args.min_prob].copy()

    # Asegura EV
    df, ev_col = ensure_ev(df)

    # Ordena por EV desc y limpia NaNs
    df[ev_col] = pd.to_numeric(df[ev_col], errors="coerce")
    df = df.dropna(subset=[ev_col]).sort_values(ev_col, ascending=False).reset_index(drop=True)

    # Límite por ticker si se pidió
    if args.per_ticker and "ticker" in df.columns:
        df = (df.groupby("ticker", group_keys=False)
                .apply(lambda g: g.head(args.per_ticker))
                .reset_index(drop=True))

    # TOP-N global si se pidió
    if args.top_n and args.top_n > 0:
        df_top = df.head(args.top_n).copy()
    else:
        df_top = df.copy()

    # Guarda resultados
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_top.to_csv(out_path, index=False, encoding="utf-8")

    # Meta
    meta = {
        "in_csv": args.in_csv,
        "out_csv": str(out_path),
        "rows_in": int(len(df)),
        "rows_out": int(len(df_top)),
        "ev_col": ev_col,
        "prob_col": prob_col,
        "min_prob": args.min_prob,
        "top_n": args.top_n,
        "per_ticker": args.per_ticker,
        "columns_present": list(df.columns),
    }
    Path(args.meta_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.meta_out).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ TOP-{args.top_n} guardado en {out_path} (EV col: {ev_col}, filas_in={len(df)}, filas_out={len(df_top)})")

if __name__ == "__main__":
    main()
