# =============================================
# 5. simulate_montecarlo.py
# =============================================
import pandas as pd, numpy as np, argparse, os

def montecarlo(df, n_sims=1000, n_trades=50):
    rets = []
    valid = df[df['gate_ok']==1]['y_hat']
    if len(valid)<5: return pd.DataFrame()
    for i in range(n_sims):
        sample = np.random.choice(valid, size=min(n_trades,len(valid)), replace=True)
        rets.append(sample.mean())
    arr = np.array(rets)
    return pd.Series({
        'mc_p10':np.percentile(arr,10),
        'mc_p50':np.percentile(arr,50),
        'mc_p90':np.percentile(arr,90),
        'mc_prob_gain':(arr>0).mean(),
        'mc_score':np.percentile(arr,50)-0.5*abs(np.percentile(arr,10))
    })

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--forecast_dir", default="reports/forecast")
    args = ap.parse_args()
    path = os.path.join(args.forecast_dir,args.month,"forecast_signals.csv")
    df = pd.read_csv(path)
    mc = montecarlo(df)
    out = os.path.join(args.forecast_dir,args.month,"forecast_mc.csv")
    mc.to_csv(out)
    print(f"[mc] Guardado {out}")

if __name__=="__main__":
    main()
