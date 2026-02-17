# Script: 13_explain_signals_shap.py
# Explica señales con SHAP y guarda resúmenes por señal
import pandas as pd
import shap
import joblib
import os

FEATURES_PATH = 'data/daily/features_daily.parquet'
MODEL_PATH = 'models/direction/rf.joblib'  # Ejemplo con RF
EXPLAIN_PATH = 'reports/shap_explanations.parquet'


def main():
    df = pd.read_parquet(FEATURES_PATH)
    X = df.drop(columns=['timestamp', 'ticker', 'target'])
    model = joblib.load(MODEL_PATH)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    # Guardar top features por señal
    top_feats = []
    for i in range(len(X)):
        vals = shap_values[i]
        top_idx = vals.argsort()[-5:][::-1]
        top = {f'feat_{j}': X.columns[idx] for j, idx in enumerate(top_idx)}
        top.update({f'shap_{j}': float(vals[idx]) for j, idx in enumerate(top_idx)})
        top['signal_idx'] = i
        top_feats.append(top)
    df_top = pd.DataFrame(top_feats)
    df_top.to_parquet(EXPLAIN_PATH, index=False)
    print(f"[OK] Explicaciones SHAP guardadas en {EXPLAIN_PATH}")

if __name__ == "__main__":
    main()
