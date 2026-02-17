# scripts/23_rank_signals.py
import argparse
import pandas as pd
import numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_csv", required=True, help="CSV con prob_win y pred_return_5d")
    ap.add_argument("--out", default="reports/forecast/ranked_signals_top30.csv")
    ap.add_argument("--top_n", type=int, default=30)
    ap.add_argument("--min_prob", type=float, default=0.62)
    ap.add_argument("--min_move_buy", type=float, default=0.012, help="mínimo +1.2% para Buys")
    ap.add_argument("--min_move_sell", type=float, default=-0.012, help="máximo -1.2% para Sells")
    args = ap.parse_args()

    df = pd.read_csv(args.in_csv)

    # Heurística expected value si no existe
    if "expected_value" not in df.columns:
        p = df["prob_win"].clip(0,1)
        loss_proxy = 0.6 * df["pred_return_5d"].abs()
        df["expected_value"] = p * df["pred_return_5d"] - (1 - p) * loss_proxy

    # Señal sugerida por dirección estimada
    df["suggested_side"] = np.where(df["pred_return_5d"] >= 0, "BUY", "SELL")

    # Filtros mínimos por lado
    mask_buy  = (df["suggested_side"] == "BUY")  & (df["pred_return_5d"] >= args.min_move_buy)
    mask_sell = (df["suggested_side"] == "SELL") & (df["pred_return_5d"] <= args.min_move_sell)
    mask_prob = (df["prob_win"] >= args.min_prob)

    df["rank_score"] = df["expected_value"]
    ranked = df[mask_prob & (mask_buy | mask_sell)].sort_values("rank_score", ascending=False)

    top = ranked.head(args.top_n).copy()
    top.to_csv(args.out, index=False)
    print(f"✅ Exportado TOP {len(top)} → {args.out}")

if __name__ == "__main__":
    main()