# =============================================
# 4. infer_and_gate.py
# =============================================
import argparse, joblib, pandas as pd, numpy as np, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--models", default="models")
    ap.add_argument("--features", default="features_labeled.csv")
    ap.add_argument("--forecast_dir", default="reports/forecast")
    ap.add_argument("--tickers-file", default="", help="Opcional: CSV con columna 'ticker' para filtrar el universo antes de inferir")
    ap.add_argument("--min-prob", type=float, default=0.55)
    ap.add_argument("--min-yhat", type=float, default=0.06)
    args = ap.parse_args()

    df = pd.read_csv(args.features)
    # Filtrar por universo si se provee tickers-file
    if args.tickers_file and os.path.exists(args.tickers_file):
        try:
            tks = pd.read_csv(args.tickers_file)['ticker'].dropna().astype(str).unique().tolist()
            df = df[df['ticker'].astype(str).isin(tks)].copy()
        except Exception:
            pass
    reg = joblib.load(f"{args.models}/return_model_H3.joblib")
    clf = joblib.load(f"{args.models}/prob_win_clean.joblib")
    X = df[['ema10','ema20','rsi14','atr_pct','vol_z']].fillna(0)
    df['y_hat'] = reg.predict(X)
    df['prob_win'] = clf.predict_proba(X)[:,1]
    df['gate_ok'] = ((df['prob_win']>=args.min_prob)&(df['y_hat'].abs()>=args.min_yhat)).astype(int)
    outdir = os.path.join(args.forecast_dir,args.month); os.makedirs(outdir,exist_ok=True)
    df.to_csv(os.path.join(outdir,"forecast_signals.csv"),index=False)
    print(f"[infer] Señales guardadas -> {outdir}")

if __name__=="__main__":
    main()
