
import os, json, yaml, argparse, pandas as pd, numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from utils import ensure_dir, month_bounds, add_basic_features, add_target

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FROZEN = os.path.join(ROOT, "data", "frozen")
REPORTS = os.path.join(ROOT, "reports")

def load_cfgs():
    with open(os.path.join(ROOT, "manifest.yaml"), "r", encoding="utf-8") as f:
        man = yaml.safe_load(f)
    with open(os.path.join(ROOT, "configs", "model.yaml"), "r", encoding="utf-8") as f:
        mod = yaml.safe_load(f)
    return man, mod

def load_frozen(ticker):
    path = os.path.join(FROZEN, f"{ticker}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe congelado: {path} (corre freeze_data.py)")
    return pd.read_parquet(path)

def prepare_xy(df, model_cfg, horizon):
    df = add_target(df, horizon=horizon)
    df = add_basic_features(df, model_cfg.get("features", {}))
    feat_cols = [c for c in df.columns if c.startswith(("ma_","ret_ma_","vol_")) or c=="log_ret"]
    out = df[["Date","Close","y_true"] + feat_cols].dropna(subset=feat_cols).copy()
    return out, feat_cols

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--train-end", required=True, help="YYYY-MM")
    args = ap.parse_args()

    month = args.month
    train_end = pd.to_datetime(args.train_end + "-28")

    man, mod = load_cfgs()
    uni = man["universe"]
    horizon = man["target"]["horizon_days"]
    rs = mod.get("random_state", 42)
    rf_params = mod.get("rf", {})
    start_m, end_m = month_bounds(month)

    rows = []
    for t in uni:
        df = load_frozen(t).copy()
        df["Ticker"] = t

        df_train = df[df["Date"]<=train_end].copy()
        if len(df_train) < 200:
            print(f"Advertencia: pocos datos para {t} ({len(df_train)})")
            continue

        Xy_train, feat_cols = prepare_xy(df_train, mod, horizon)
        X_train, y_train = Xy_train[feat_cols], Xy_train["y_true"]

        model = RandomForestRegressor(random_state=rs, **rf_params)
        model.fit(X_train, y_train)

        # ALL for forecasting
        Xy_all, _ = prepare_xy(df, mod, horizon)
        mask = (Xy_all["Date"]>=start_m) & (Xy_all["Date"]<=end_m)
        Xm = Xy_all.loc[mask, feat_cols]
        if len(Xm)==0: 
            continue

        yhat = model.predict(Xm)
        part = Xy_all.loc[mask, ["Date","y_true"]].copy()
        part["Ticker"] = t
        part["y_pred"] = yhat
        part["error_abs"] = (part["y_true"] - part["y_pred"]).abs()
        part["within_10pct"] = np.where(part["y_true"].notna(),
                                        (part["error_abs"] <= part["y_true"].abs()*0.10).astype(int),
                                        np.nan)
        rows.append(part)

    if not rows:
        print("Sin filas para el mes solicitado.")
        return

    out = pd.concat(rows).sort_values(["Ticker","Date"])
    out_dir = os.path.join(REPORTS, "forecast", month, "validation")
    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, "predictions.csv")
    out.to_csv(out_path, index=False, encoding="utf-8")
    print("Guardado:", out_path)

if __name__ == "__main__":
    main()
