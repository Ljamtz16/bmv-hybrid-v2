# =============================================
# 28_enforce_position_sizing.py
# =============================================
import argparse, os, math
import pandas as pd
import numpy as np

def calc_shares(entry_price, per_trade_cash, allow_fractional):
    if entry_price is None or not (entry_price > 0):
        return np.nan
    if allow_fractional:
        return per_trade_cash / float(entry_price)
    return math.floor(per_trade_cash / float(entry_price))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--dir", default="reports/forecast")
    ap.add_argument("--per-trade-cash", type=float, default=200.0)
    ap.add_argument("--allow-fractional", action="store_true")
    ap.add_argument("--in-file", default="simulate_results.csv")
    ap.add_argument("--out-file", default="simulate_results_with_shares.csv")
    args = ap.parse_args()

    path = os.path.join(args.dir, args.month, args.in_file)
    if not os.path.exists(path):
        raise SystemExit(f"No existe: {path}")

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    for col in ["entry_price", "exit_price"]:
        if col not in df.columns:
            df[col] = np.nan

    df["shares"] = df["entry_price"].apply(lambda p: calc_shares(p, args.per_trade_cash, args.allow_fractional))
    df["cash_used"] = df[["shares","entry_price"]].prod(axis=1)
    if "exit_price" in df.columns:
        df["pnl_reconstructed"] = (df["exit_price"] - df["entry_price"]) * df["shares"]

    out_path = os.path.join(args.dir, args.month, args.out_file)
    df.to_csv(out_path, index=False)
    print(f"[sizing] Escrito -> {out_path} (rows={len(df)})")

if __name__ == "__main__":
    main()
