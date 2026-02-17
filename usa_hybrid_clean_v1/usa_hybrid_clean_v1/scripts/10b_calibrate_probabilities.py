# Script: 10b_calibrate_probabilities.py
# Calibra probabilidades (isotónica/Platt) por sector y régimen, guarda calibradores y métricas
import pandas as pd
import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
import joblib
import os
import matplotlib.pyplot as plt

FEATURES_PATH = 'data/daily/features_with_targets.parquet'
MODEL_DIR = 'models/direction/'
CALIB_DIR = 'models/calibration/'


def calibrate_probs(y_true, prob_pred, method='isotonic'):
    if method == 'isotonic':
        calibrator = IsotonicRegression(out_of_bounds='clip')
        calibrator.fit(prob_pred, y_true)
    else:
        calibrator = LogisticRegression()
        calibrator.fit(prob_pred.reshape(-1,1), y_true)
    return calibrator

def main():
    print("[INFO] Cargando datos y modelos...")
    df = pd.read_parquet(FEATURES_PATH)
    df = df.dropna(subset=['target'])
    
    feature_cols = ['ret_1d', 'ret_5d', 'ret_20d', 'vol_5d', 'vol_20d', 'atr_14d', 'pos_in_range_20d']
    X = df[feature_cols]
    y = df['target'].astype(int)
    
    # Cargar meta-learner
    meta = joblib.load(MODEL_DIR + 'meta.joblib')
    rf = joblib.load(MODEL_DIR + 'rf.joblib')
    xgb = joblib.load(MODEL_DIR + 'xgb.joblib')
    cat = joblib.load(MODEL_DIR + 'cat.joblib')
    
    # Generar predicciones stacked
    print("[INFO] Generando predicciones del ensemble...")
    rf_pred = rf.predict_proba(X)[:, 1].reshape(-1, 1)
    xgb_pred = xgb.predict_proba(X)[:, 1].reshape(-1, 1)
    cat_pred = cat.predict_proba(X)[:, 1].reshape(-1, 1)
    X_meta = np.hstack([rf_pred, xgb_pred, cat_pred])
    prob_pred = meta.predict_proba(X_meta)[:, 1]
    
    print("[INFO] Calibrando probabilidades...")
    calibrator = calibrate_probs(y, prob_pred, method='isotonic')
    os.makedirs(CALIB_DIR, exist_ok=True)
    joblib.dump(calibrator, CALIB_DIR+'calibrator.joblib')
    # Métricas
    prob_cal = calibrator.predict(prob_pred.reshape(-1,1)) if hasattr(calibrator, 'predict') else calibrator.transform(prob_pred.reshape(-1,1))
    brier = brier_score_loss(y, prob_cal)
    print(f'[OK] Calibrador guardado. Brier: {brier:.4f}')
    # Reliability diagram
    frac_pos, mean_pred = calibration_curve(y, prob_cal, n_bins=10)
    plt.plot(mean_pred, frac_pos, marker='o')
    plt.plot([0,1],[0,1],'--')
    plt.xlabel('Predicted')
    plt.ylabel('Actual')
    plt.title('Reliability Diagram')
    plt.savefig(CALIB_DIR+'reliability_diagram.png')
    print(f'[OK] Reliability diagram guardado')

if __name__ == "__main__":
    main()
