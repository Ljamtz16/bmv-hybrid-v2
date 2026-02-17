# =============================================
# 3. train_models.py
# =============================================
import pandas as pd, argparse, joblib
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="features_labeled.csv")
    ap.add_argument("--outdir", default="models")
    args = ap.parse_args()

    df = pd.read_csv(args.features).dropna(subset=['y_H3'])
    X = df[['ema10','ema20','rsi14','atr_pct','vol_z']].fillna(0)
    y_reg = df['y_H3']
    y_clf = (y_reg > 0).astype(int)
    X_train,X_test,y_train,y_test=train_test_split(X,y_reg,test_size=0.2,random_state=42)

    reg = RandomForestRegressor(n_estimators=200, random_state=42)
    clf = RandomForestClassifier(n_estimators=200, random_state=42)
    reg.fit(X_train,y_train); clf.fit(X_train,(y_train>0).astype(int))

    import os; os.makedirs(args.outdir, exist_ok=True)
    joblib.dump(reg, f"{args.outdir}/return_model_H3.joblib")
    joblib.dump(clf, f"{args.outdir}/prob_win_clean.joblib")
    print("[train] Modelos guardados en", args.outdir)

if __name__=="__main__":
    main()
