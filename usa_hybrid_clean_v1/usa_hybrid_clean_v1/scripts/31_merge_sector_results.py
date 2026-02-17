import argparse, os, glob, re, pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--dir", default="reports/forecast")
    ap.add_argument("--pattern", default="simulate_results_sector_*.csv")
    ap.add_argument("--out", default="simulate_results_all.csv")
    args = ap.parse_args()

    folder = os.path.join(args.dir, args.month)
    # Prefer canonical current-run files only (avoid timestamped snapshots)
    canonical = [
        os.path.join(folder, f)
        for f in [
            "simulate_results_sector_tech.csv",
            "simulate_results_sector_financials.csv",
            "simulate_results_sector_energy.csv",
            "simulate_results_sector_defensive.csv",
            "simulate_results.csv",
        ]
        if os.path.exists(os.path.join(folder, f))
    ]

    files = canonical.copy()
    if not files:
        # Fallback to pattern but filter out timestamped snapshot files like *_YYYYMMDD_HHMMSS.csv
        cand = glob.glob(os.path.join(folder, args.pattern))
        ts_re = re.compile(r"_\d{8}_\d{6}\.csv$")
        files = [f for f in cand if not ts_re.search(os.path.basename(f))]
        if not files:
            cand2 = glob.glob(os.path.join(folder, "*sector*.csv"))
            files = [f for f in cand2 if not ts_re.search(os.path.basename(f))]
            if not files:
                default = os.path.join(folder, "simulate_results.csv")
                if os.path.exists(default):
                    files = [default]
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            if not df.empty:
                df["__source"] = os.path.basename(f)
                dfs.append(df)
        except Exception:
            pass

    if not dfs:
        default_f = os.path.join(folder, "simulate_results.csv")
        if os.path.exists(default_f):
            try:
                df = pd.read_csv(default_f)
                if not df.empty:
                    df["__source"] = "simulate_results.csv"
                    dfs = [df]
            except Exception:
                pass

    outp = os.path.join(folder, args.out)
    if dfs:
        merged = pd.concat(dfs, ignore_index=True)
        # Light dedupe to avoid exact duplicates across sectors (by ticker+entry_dt if present)
        cols = [c.lower().strip() for c in merged.columns]
        merged.columns = cols
        if "entry_dt" not in merged.columns and "entry_date" in merged.columns:
            merged["entry_dt"] = pd.to_datetime(merged["entry_date"], errors="coerce")
        elif "entry_dt" in merged.columns:
            merged["entry_dt"] = pd.to_datetime(merged["entry_dt"], errors="coerce")
        keys = [k for k in ["ticker", "entry_dt"] if k in merged.columns]
        before = len(merged)
        if keys:
            merged = merged.drop_duplicates(subset=keys, keep="first")
        after = len(merged)
        if after < before:
            print(f"[merge] (sector) Deduplicados {before-after} de {before} registros (claves: {keys})")
        merged.to_csv(outp, index=False)
        print(f"[merge] {args.month}: {len(dfs)} archivos -> {outp}")
    else:
        # No crear/alterar all.csv si no hay fuentes; deja el existente para trazabilidad
        print(f"[merge] {args.month}: no hay archivos a unir (se conserva simulate_results_all.csv si ya existía)")

if __name__ == "__main__":
    main()
