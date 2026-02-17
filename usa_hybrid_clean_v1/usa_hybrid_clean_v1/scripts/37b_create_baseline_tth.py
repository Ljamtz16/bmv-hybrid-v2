# =============================================
# 37b_create_baseline_tth.py
# =============================================
"""
Crea modelos TTH baseline basados en heurísticas simples
cuando no hay suficientes datos históricos.

Útil para bootstrap inicial del sistema.
"""

import pandas as pd
import numpy as np
import joblib
import os
import json
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

def create_baseline_hazard_models(max_days=5):
    """
    Crea modelos hazard baseline con comportamiento heurístico.
    """
    print("[baseline_tth] Creando modelos hazard baseline...")
    
    # Generar datos sintéticos basados en heurísticas conocidas
    np.random.seed(42)
    n_samples = 200
    
    # Features sintéticas
    data = {
        'prob_win': np.random.beta(6, 4, n_samples),  # Sesgo hacia 0.6
        'abs_y_hat': np.random.gamma(2, 0.03, n_samples),  # Retornos esperados
        'tp_pct': np.random.normal(0.06, 0.01, n_samples),
        'sl_pct': np.random.normal(0.01, 0.002, n_samples),
        'atr_pct': np.random.gamma(2, 0.01, n_samples),  # Volatilidad
        'rsi14': np.random.normal(55, 15, n_samples),
        'vol_z': np.random.normal(0, 1, n_samples),
        'pattern_weight': np.ones(n_samples),
        'pscore_adj': np.ones(n_samples),
        'double_top': np.random.binomial(1, 0.1, n_samples),
        'double_bottom': np.random.binomial(1, 0.1, n_samples),
    }
    
    df = pd.DataFrame(data)
    
    models_tp = {}
    models_sl = {}
    
    feature_cols = list(data.keys())
    
    # Entrenar por día
    for k in range(1, max_days + 1):
        # TP: probabilidad aumenta con prob_win y abs_y_hat
        # Mayor en días medios (día 2-3)
        y_tp = (
            (df['prob_win'] > 0.6) & 
            (df['abs_y_hat'] > 0.04) &
            (np.random.rand(n_samples) < (0.3 if k <= 3 else 0.1))
        ).astype(int)
        
        if y_tp.sum() >= 5:
            clf_tp = RandomForestClassifier(
                n_estimators=50,
                max_depth=3,
                random_state=42
            )
            clf_tp.fit(df[feature_cols], y_tp)
            models_tp[k] = clf_tp
            print(f"  Día {k} (TP): {y_tp.sum()} eventos positivos")
        
        # SL: probabilidad aumenta con volatilidad, menor prob_win
        y_sl = (
            (df['prob_win'] < 0.5) &
            (df['atr_pct'] > 0.025) &
            (np.random.rand(n_samples) < (0.15 if k <= 2 else 0.05))
        ).astype(int)
        
        if y_sl.sum() >= 5:
            clf_sl = RandomForestClassifier(
                n_estimators=50,
                max_depth=3,
                random_state=42
            )
            clf_sl.fit(df[feature_cols], y_sl)
            models_sl[k] = clf_sl
            print(f"  Día {k} (SL): {y_sl.sum()} eventos positivos")
    
    return models_tp, models_sl, feature_cols

def create_baseline_mc_models():
    """
    Crea modelos MC baseline para mu y sigma.
    """
    print("[baseline_tth] Creando modelos Monte Carlo baseline...")
    
    np.random.seed(42)
    n_samples = 200
    
    # Features
    data = {
        'abs_y_hat': np.random.gamma(2, 0.03, n_samples),
        'atr_pct': np.random.gamma(2, 0.01, n_samples),
        'prob_win': np.random.beta(6, 4, n_samples),
        'horizon_days': np.random.choice([3, 4, 5], n_samples),
    }
    
    df = pd.DataFrame(data)
    
    # mu ~ abs_y_hat / horizon (retorno por día)
    mu = df['abs_y_hat'] / df['horizon_days']
    
    # sigma ~ atr_pct con ruido
    sigma = df['atr_pct'] * (1 + np.random.normal(0, 0.2, n_samples))
    
    # Entrenar regresores
    feature_cols = list(data.keys())
    
    mu_model = RandomForestRegressor(n_estimators=50, max_depth=3, random_state=42)
    mu_model.fit(df[feature_cols], mu)
    
    sigma_model = RandomForestRegressor(n_estimators=50, max_depth=3, random_state=42)
    sigma_model.fit(df[feature_cols], sigma)
    
    print(f"  mu_mean={mu.mean():.4f}, sigma_mean={sigma.mean():.4f}")
    
    return {
        'mu_model': mu_model,
        'sigma_model': sigma_model,
        'feature_cols': feature_cols
    }

def main():
    print("[baseline_tth] === CREANDO MODELOS TTH BASELINE ===")
    print("[baseline_tth] NOTA: Estos son modelos heurísticos para bootstrap")
    print("[baseline_tth] Entrena con datos reales cuando tengas ≥50 trades\n")
    
    # Crear modelos
    models_tp, models_sl, feature_cols = create_baseline_hazard_models(max_days=5)
    mc_bundle = create_baseline_mc_models()
    
    # Guardar
    os.makedirs('models', exist_ok=True)
    
    # Hazard
    hazard_bundle = {
        'models_tp': models_tp,
        'models_sl': models_sl,
        'feature_cols': feature_cols,
        'max_days': 5,
        'is_baseline': True
    }
    
    joblib.dump(hazard_bundle, 'models/tth_hazard_discrete.joblib')
    print("\n[baseline_tth] Hazard discreto → models/tth_hazard_discrete.joblib")
    
    # Monte Carlo
    mc_bundle['is_baseline'] = True
    joblib.dump(mc_bundle, 'models/tth_monte_carlo.joblib')
    print("[baseline_tth] Monte Carlo → models/tth_monte_carlo.joblib")
    
    # Metadata
    metadata = {
        'baseline': True,
        'warning': 'Modelos heurísticos - entrenar con datos reales',
        'max_days': 5,
        'feature_cols': feature_cols,
        'tp_models': len(models_tp),
        'sl_models': len(models_sl),
        'mc_calibrated': True
    }
    
    with open('models/tth_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print("[baseline_tth] Metadata → models/tth_metadata.json")
    print("\n[baseline_tth] ✓ Modelos baseline creados")
    print("[baseline_tth] Ahora puedes ejecutar 39_predict_time_to_hit.py")

if __name__ == "__main__":
    main()
