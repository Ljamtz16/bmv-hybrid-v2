# =============================================
# 25_join_backtests.py
# =============================================
import glob, pandas as pd, argparse, os

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dir",default="reports/forecast")
    ap.add_argument("--out",default="reports/backtests_joined.csv")
    args=ap.parse_args()

    files=glob.glob(os.path.join(args.dir,"*/simulate_results.csv"))
    dfs=[pd.read_csv(f).assign(month=os.path.basename(os.path.dirname(f))) for f in files]
    out=pd.concat(dfs,ignore_index=True)
    out.to_csv(args.out,index=False)
    print(f"[join] {len(out)} meses -> {args.out}")

if __name__=="__main__":
    main()