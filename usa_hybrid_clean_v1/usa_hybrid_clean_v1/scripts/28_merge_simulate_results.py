# =============================================
# 28_merge_simulate_results.py
# =============================================
# Une simulate_results*.csv de un mes en un único simulate_results_merged.csv
# con deduplicación agresiva por (ticker, entry_date) y opcionalmente salida/rr.
# Uso:
#   python scripts/28_merge_simulate_results.py --month 2025-10 \
#       --in-dir reports/forecast --out-dir reports/forecast

import argparse, os
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--in-dir", default="reports/forecast")
    ap.add_argument("--out-dir", default="reports/forecast")
    args = ap.parse_args()

    mdir = os.path.join(args.in_dir, args.month)
    files = [
        os.path.join(mdir, f) for f in os.listdir(mdir)
        if f.startswith("simulate_results") and f.endswith(".csv")
    ]
    if not files:
        raise SystemExit(f"No hay simulate_results*.csv en {mdir}")

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            df.columns = [c.strip().lower() for c in df.columns]
            df["__source_file"] = os.path.basename(f)
            dfs.append(df)
        except Exception as e:
            print(f"[merge] Aviso: no se pudo leer {f}: {e}")

    if not dfs:
        raise SystemExit("No se pudo leer ningún simulate_results*.csv")

    big = pd.concat(dfs, ignore_index=True)
    # Normalizar claves
    if "entry_dt" not in big.columns and "entry_date" in big.columns:
        big["entry_dt"] = pd.to_datetime(big["entry_date"], errors="coerce")
    elif "entry_dt" in big.columns:
        big["entry_dt"] = pd.to_datetime(big["entry_dt"], errors="coerce")

    if "exit_dt" in big.columns:
        big["exit_dt"] = pd.to_datetime(big["exit_dt"], errors="coerce")

    keys = [k for k in ["ticker","entry_dt"] if k in big.columns]
    # Más robusto si hay rr o pnl
    for k in ["rr","pnl"]:
        if k in big.columns:
            keys.append(k)
            break

    before = len(big)
    if keys:
        big = big.drop_duplicates(subset=keys, keep="first")
    after = len(big)
    if after < before:
        print(f"[merge] Deduplicados {before-after} de {before} registros (claves: {keys})")

    out_dir = os.path.join(args.out_dir, args.month)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "simulate_results_merged.csv")
    big.to_csv(out_file, index=False)
    print(f"[merge] Guardado -> {out_file} (rows={len(big)})")


if __name__ == "__main__":
    main()
