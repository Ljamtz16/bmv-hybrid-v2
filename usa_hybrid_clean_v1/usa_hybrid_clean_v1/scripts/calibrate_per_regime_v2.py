"""
Script: calibrate_per_regime_v2.py
Calibración robusta por régimen:
1. Temperature scaling (T=1.5) para desaturar probabilidades
2. Isotonic + Platt por régimen
3. Blend 50/50 para estabilidad
"""
import os
import pandas as pd
import numpy as np
import joblib
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

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

    print("="*60)
    print("CALIBRACIÓN POR RÉGIMEN (Temperature + Isotonic + Platt)")
    print("="*60)
    
    # 1. Temperature scaling global para desaturar
    df['prob_temp'] = apply_temperature_scaling(df['prob_raw'].values, temperature=1.5)
    print(f"\n[INFO] Temperature scaling aplicado (T=1.5)")
    
    models_iso = {}
    models_platt = {}
    
    # 2. Fit calibradores por régimen
    for regime in ['low_vol','med_vol','high_vol']:
        sub = df[df['regime']==regime].copy()
        if len(sub) < 200:
            print(f"[WARN] Regime {regime}: pocos datos ({len(sub)}). Se omite.")
            continue
        
        y = sub['target'].astype(int).values
        p_temp = sub['prob_temp'].values
        
        # Fit isotonic
        iso = fit_isotonic(y, p_temp)
        models_iso[regime] = iso
        
        # Fit Platt
        platt = fit_platt(y, p_temp)
        models_platt[regime] = platt
        
        # Guardar ambos
        joblib.dump(iso, os.path.join(OUT_DIR, f'calibrator_iso_{regime}.joblib'))
        joblib.dump(platt, os.path.join(OUT_DIR, f'calibrator_platt_{regime}.joblib'))
        
        print(f"[OK] {regime:10s}: {len(sub)} muestras → calibradores guardados")

    # 3. Aplicar blend 50/50 isotonic + platt
    def apply_calib(row):
        reg = row['regime']
        p_temp = float(np.clip(row['prob_temp'], 1e-6, 1-1e-6))
        
        iso_model = models_iso.get(reg)
        platt_model = models_platt.get(reg)
        
        if iso_model is None or platt_model is None:
            return p_temp
        
        p_iso = float(iso_model.predict([p_temp])[0])
        
        logit_temp = np.log(p_temp / (1 - p_temp))
        p_platt = float(platt_model.predict_proba([[logit_temp]])[0, 1])
        
        # Blend 50/50
        p_final = 0.5 * p_iso + 0.5 * p_platt
        return np.clip(p_final, 1e-6, 1-1e-6)

    if models_iso:
        print("\n[INFO] Aplicando blend isotonic/platt...")
        df['prob_calibrated'] = df.apply(apply_calib, axis=1)
        out_parquet = 'val/oos_predictions_calibrated.parquet'
        df.to_parquet(out_parquet, index=False)
        print(f"[OK] Predicciones OOS calibradas → {out_parquet}")
        
        # 4. Métricas rápidas antes/después
        y_true = df['target'].values
        brier_raw = brier_score_loss(y_true, df['prob_raw'])
        brier_cal = brier_score_loss(y_true, df['prob_calibrated'])
        auc_raw = roc_auc_score(y_true, df['prob_raw'])
        auc_cal = roc_auc_score(y_true, df['prob_calibrated'])
        
        print("\n" + "="*60)
        print("MÉTRICAS RÁPIDAS (antes/después calibración)")
        print("="*60)
        print(f"AUC:   {auc_raw:.4f} → {auc_cal:.4f} {'✅' if abs(auc_cal-auc_raw)<0.03 else '⚠️'}")
        print(f"Brier: {brier_raw:.4f} → {brier_cal:.4f} {'✅' if brier_cal<0.13 else '⚠️'}")
        
        # ECE quick estimate
        bins_edge = np.linspace(0,1,11)
        df['bin'] = np.digitize(df['prob_calibrated'], bins_edge) - 1
        ece_per_bin = df.groupby('bin', dropna=False).apply(
            lambda g: abs(g['target'].mean() - g['prob_calibrated'].mean()) if len(g)>0 else 0.0
        )
        ece = ece_per_bin.mean()
        print(f"ECE:   {ece:.4f} {'✅' if ece<0.05 else '⚠️ (objetivo <0.05)'}")
        
    else:
        print("[WARN] No se calibró ningún régimen por falta de datos.")

if __name__ == '__main__':
    main()
