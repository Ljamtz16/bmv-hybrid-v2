
import os, json, argparse, pandas as pd, numpy as np
from utils import ensure_dir

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
REPORTS = os.path.join(ROOT, "reports")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    args = ap.parse_args()

    pred_path = os.path.join(REPORTS, "forecast", args.month, "validation", "predictions.csv")
    if not os.path.exists(pred_path):
        raise FileNotFoundError(f"No existe {pred_path}")
    df = pd.read_csv(pred_path, parse_dates=["Date"])
    df = df.dropna(subset=["y_true"])
    if len(df)==0:
        print("No hay y_true para KPIs (mes aún no cerrado).")
        return

    err = (df["y_true"] - df["y_pred"]).abs()
    mape = (err / df["y_true"].abs().replace(0, np.nan)).dropna().mean()
    mae = err.mean()
    within = (df["within_10pct"]==1).mean()

    kpis = {"rows": int(len(df)), "mae": float(mae), "mape": float(mape), "within_10pct_rate": float(within)}
    out_dir = os.path.join(REPORTS, "forecast", args.month, "validation")
    ensure_dir(out_dir)
    with open(os.path.join(out_dir, "kpis.json"), "w", encoding="utf-8") as f:
        json.dump(kpis, f, indent=2, ensure_ascii=False)
    print("KPIs:", kpis)

if __name__ == "__main__":
    main()
