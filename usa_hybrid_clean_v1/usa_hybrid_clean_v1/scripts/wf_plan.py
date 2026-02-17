# =============================================
# 7. wf_plan.py
# =============================================
import pandas as pd, numpy as np, argparse, os, json

def simulate_policy(df, tp, sl):
    wins = (df['y_hat']>=tp).sum(); losses=(df['y_hat']<=-sl).sum()
    total=len(df); rr=(wins-losses)/max(1,total)
    return {'tp':tp,'sl':sl,'rr':rr}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-end-jan", required=True)
    ap.add_argument("--train-end-forward", required=True)
    ap.add_argument("--back-k", type=int, default=3)
    ap.add_argument("--metric", default="net_rr")
    ap.add_argument("--lambda", type=float, default=0.5)
    ap.add_argument("--tickers", default="", help="Archivo CSV con tickers sectoriales")
    args = ap.parse_args()

    combos=[(0.05,0.01),(0.07,0.01),(0.1,0.02)]
    month_dir = getattr(args, 'train_end_forward', '2025-10')
    forecast_path = f"reports/forecast/{month_dir}/forecast_signals.csv"
    df=pd.read_csv(forecast_path)
    # Filtrar por tickers si se especifica archivo
    if args.tickers and os.path.exists(args.tickers):
        tickers_list = pd.read_csv(args.tickers)['ticker'].tolist()
        df = df[df['ticker'].isin(tickers_list)]
    results=[simulate_policy(df,tp,sl) for tp,sl in combos]
    best=max(results,key=lambda x:x['rr'])
    os.makedirs("reports/policies",exist_ok=True)
    with open("reports/policies/Policy_USA_AUTO.json","w") as f: json.dump(best,f,indent=2)
    print("[wf] Política óptima:",best)

if __name__=="__main__":
    main()


