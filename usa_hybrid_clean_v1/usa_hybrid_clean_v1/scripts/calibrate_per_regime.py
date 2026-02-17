import os
import pandas as pd
import numpy as np
import joblib
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

VAL_PRED_PATH = 'val/oos_predictions.parquet'
REGIME_PATH = 'data/daily/regime_daily.csv'
OUT_DIR = 'models/calibration/'

def apply_temperature_scaling(p, temperature=1.5):
    """Suaviza probabilidades extremas mediante temperatura."""
    p = np.clip(p, 1e-6, 1-1e-6)
    logit = np.log(p / (1 - p))
    p_scaled = 1 / (1 + np.exp(-logit / temperature))
    return np.clip(p_scaled, 1e-6, 1-1e-6)

def fit_isotonic(y, p):
    """Ajusta calibrador isotónico (preserva orden, suaviza bins)."""
    p = np.clip(p, 1e-6, 1-1e-6)
    ir = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True, out_of_bounds='clip')
    ir.fit(p, y)
    return ir

def fit_platt(y, p):
    """Ajusta calibrador Platt (regresión logística sobre logit)."""
    p = np.clip(p, 1e-6, 1-1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    lr = LogisticRegression(max_iter=1000, solver='lbfgs')
    lr.fit(logit, y)
    return lr

def main():
    if not os.path.exists(VAL_PRED_PATH):
        print(f"[ERR] No existe {VAL_PRED_PATH}. Ejecute walk-forward primero.")
        return
    os.makedirs(OUT_DIR, exist_ok=True)

    df = pd.read_parquet(VAL_PRED_PATH)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.rename(columns={'prob_pred': 'prob_raw', 'y_true': 'target'})

    regime_df = pd.read_csv(REGIME_PATH)
    regime_df['timestamp'] = pd.to_datetime(regime_df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    regime_df['date'] = regime_df['timestamp'].dt.date
    df = df.merge(regime_df[['date', 'ticker', 'regime']], on=['date', 'ticker'], how='left')

    models = {}
    for regime in ['low_vol','med_vol','high_vol']:
        sub = df[df['regime']==regime]
        if len(sub) < 200:
            print(f"[WARN] Regime {regime}: pocos datos ({len(sub)}). Se omite.")
            continue
        ir = fit_isotonic(sub['target'].astype(int).values, sub['prob_raw'].values)
        joblib.dump(ir, os.path.join(OUT_DIR, f'calibrator_{regime}.joblib'))
        models[regime] = ir
        print(f"[OK] Calibrador guardado: calibrator_{regime}.joblib ({len(sub)} muestras)")

    # Generar archivo con prob_calibrated_regime
    def apply_calib(row):
        reg = row['regime']
        pr = float(np.clip(row['prob_raw'], 1e-6, 1-1e-6))
        model = models.get(reg)
        if model is None:
            return pr
        return float(model.predict([pr])[0])

    if models:
        df['prob_calibrated'] = df.apply(apply_calib, axis=1)
        out_parquet = 'val/oos_predictions_calibrated.parquet'
        df.to_parquet(out_parquet, index=False)
        print(f"[OK] Predicciones OOS calibradas por régimen -> {out_parquet}")
    else:
        print("[WARN] No se calibró ningún régimen por falta de datos.")

if __name__ == '__main__':
    main()
