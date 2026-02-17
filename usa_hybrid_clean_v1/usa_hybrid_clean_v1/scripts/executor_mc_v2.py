# =============================================
# 6. executor_mc_v2.py
# =============================================
import pandas as pd, argparse, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--forecast_dir", default="reports/forecast")
    args = ap.parse_args()

    f_fore = os.path.join(args.forecast_dir,args.month,"forecast_signals.csv")
    df = pd.read_csv(f_fore)
    df = df[df['gate_ok']==1]
    df = df[(df['volume']>0)&(df['atr_pct']<0.05)]
    out = os.path.join(args.forecast_dir,args.month,"forecast_with_mc_validated.csv")
    df.to_csv(out,index=False)
    print(f"[exec] {len(df)} operaciones válidas -> {out}")

if __name__=="__main__":
    main()
