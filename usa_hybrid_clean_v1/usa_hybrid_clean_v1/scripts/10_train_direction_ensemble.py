# Script: 10_train_direction_ensemble.py
# Entrena modelos base (RF, XGBoost, CatBoost) y meta-learner para stacking/blending
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import joblib
import os

FEATURES_PATH = 'data/daily/features_with_targets.parquet'
MODEL_DIR = 'models/direction/'


def load_data():
    df = pd.read_parquet(FEATURES_PATH)
    df = df.dropna(subset=['target'])  # Solo samples con label
    
    # Features para modelo
    feature_cols = ['ret_1d', 'ret_5d', 'ret_20d', 'vol_5d', 'vol_20d', 'atr_14d', 'pos_in_range_20d']
    X = df[feature_cols]
    y = df['target']
    
    print(f"[INFO] Dataset: {len(X)} samples, {X.shape[1]} features")
    print(f"[INFO] Target balance: {y.mean():.2%} positive")
    
    return X, y

def train_ensemble(X, y):
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    xgb = XGBClassifier(n_estimators=100, random_state=42, use_label_encoder=False, eval_metric='logloss')
    cat = CatBoostClassifier(iterations=100, verbose=0, random_state=42)
    rf.fit(X_train, y_train)
    xgb.fit(X_train, y_train)
    cat.fit(X_train, y_train)
    # Meta-learner (stacking)
    val_preds = np.column_stack([
        rf.predict_proba(X_val)[:,1],
        xgb.predict_proba(X_val)[:,1],
        cat.predict_proba(X_val)[:,1]
    ])
    meta = LogisticRegression()
    meta.fit(val_preds, y_val)
    # Save models
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(rf, MODEL_DIR+'rf.joblib')
    joblib.dump(xgb, MODEL_DIR+'xgb.joblib')
    joblib.dump(cat, MODEL_DIR+'cat.joblib')
    joblib.dump(meta, MODEL_DIR+'meta.joblib')
    print('[OK] Modelos base y meta-learner guardados')
    # Métrica
    auc = roc_auc_score(y_val, meta.predict_proba(val_preds)[:,1])
    print(f'[AUC] Ensemble stacking: {auc:.4f}')

def main():
    X, y = load_data()
    train_ensemble(X, y)

if __name__ == "__main__":
    main()
