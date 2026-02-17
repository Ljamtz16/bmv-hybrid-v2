# scripts/21_train_prob_model.py
import argparse, os, joblib, pandas as pd, numpy as np
from sklearn.model_selection import TimeSeriesSplit, RandomizedSearchCV
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV

NUM_FEATS = ["tp", "sl"]
CAT_FEATS = ["ticker", "side", "reason"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="reports/forecast/training_dataset.csv")
    ap.add_argument("--model_out", default="models/prob_win_calibrated.joblib")
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    df = df.dropna(subset=["y"])  # asegúrate de tener etiqueta
    y = df["y"].astype(int).values

    # Feature engineering simple opcional
    if all(c in df.columns for c in ["tp","sl"]):
        df["rrr_abs"] = (df["tp"] - df["sl"]).abs()
        NUM = NUM_FEATS + ["rrr_abs"]
    else:
        NUM = NUM_FEATS

    X = df[NUM + CAT_FEATS].copy()

    pre = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUM),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=5), CAT_FEATS),
        ]
    )

    # Pipeline: prepro + modelo base
    pipe = Pipeline([
        ("pre", pre),
        ("clf", RandomForestClassifier(random_state=42, n_jobs=-1))
    ])
    # Búsqueda de hiperparámetros sobre el pipeline completo
    param_dist = {
        "clf__n_estimators": [100, 200, 400, 600],
        "clf__max_depth": [None, 5, 10, 20],
        "clf__min_samples_leaf": [1, 3, 5, 10]
    }
    search = RandomizedSearchCV(pipe, param_distributions=param_dist,
                                n_iter=10, cv=TimeSeriesSplit(n_splits=5), scoring="roc_auc", random_state=42)
    search.fit(X, y)
    print("Mejores hiperparámetros:", search.best_params_)
    print("AUC (cv):", search.best_score_)
    # Usar el mejor pipeline para calibración
    base = search.best_estimator_.named_steps["clf"]
    clf_cal = Pipeline(steps=[
        ("pre", pre),
        ("cal", CalibratedClassifierCV(base, method="sigmoid", cv=5))
    ])
    clf_cal.fit(X, y)

    # Métricas in-sample (orientativas)
    proba_in = clf_cal.predict_proba(X)[:,1]
    print("AUC (in):", roc_auc_score(y, proba_in))
    print("Brier (in):", brier_score_loss(y, proba_in))

    os.makedirs(os.path.dirname(args.model_out), exist_ok=True)
    joblib.dump({"model": clf_cal, "num_feats": NUM, "cat_feats": CAT_FEATS}, args.model_out)
    print(f"✅ Modelo guardado en {args.model_out}")

if __name__ == "__main__":
    main()
