# =============================================
# 38_train_time_to_hit.py
# =============================================
"""
Entrena modelos de Time-to-Hit usando:
1. Random Survival Forest (supervivencia)
2. Hazard discreto (logística por día)
3. Monte Carlo calibrado (baseline)

Output: models/tth_*.joblib
"""

import pandas as pd
import numpy as np
import argparse
import os
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import json

def train_hazard_discrete(df_train, df_test, max_days=5):
    """
    Entrena modelos de hazard discreto: P(evento en día k | sobrevivió hasta k-1).
    Un modelo por cada día y evento (TP/SL).
    """
    models_tp = {}
    models_sl = {}
    
    print(f"\n[train_hazard] Entrenando hazard discreto (max_days={max_days})")
    
    # Features
    feature_cols = [
        'prob_win', 'abs_y_hat', 'tp_pct', 'sl_pct', 
        'atr_pct', 'rsi14', 'vol_z',
        'pattern_weight', 'pscore_adj',
        'double_top', 'double_bottom'
    ]
    
    # Entrenar por día para TP
    for k in range(1, max_days + 1):
        print(f"  Día {k} (TP)...", end="")
        
        # Etiqueta: 1 si TP ocurrió exactamente en día k, 0 si no (sobrevivió más o fue SL/censura)
        y_train = ((df_train['event_type'] == 'TP') & 
                   (df_train['time_to_event_days'] == k)).astype(int)
        
        # Solo entrenar con los que sobrevivieron hasta k-1
        mask_train = df_train['time_to_event_days'] >= k
        
        if mask_train.sum() < 10:
            print(f" SKIP (datos insuficientes)")
            continue
        
        X_train_k = df_train.loc[mask_train, feature_cols].fillna(0)
        y_train_k = y_train[mask_train]
        
        if y_train_k.sum() < 2:
            print(f" SKIP (sin eventos positivos)")
            continue
        
        # Entrenar
        clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=10,
            random_state=42,
            class_weight='balanced'
        )
        clf.fit(X_train_k, y_train_k)
        models_tp[k] = clf
        
        # Evaluación
        if len(df_test) > 0:
            mask_test = df_test['time_to_event_days'] >= k
            if mask_test.sum() > 0:
                X_test_k = df_test.loc[mask_test, feature_cols].fillna(0)
                y_test_k = ((df_test['event_type'] == 'TP') & 
                            (df_test['time_to_event_days'] == k)).astype(int)[mask_test]
                score = clf.score(X_test_k, y_test_k)
                print(f" acc={score:.3f}")
            else:
                print(" OK")
        else:
            print(" OK")
    
    # Entrenar por día para SL
    for k in range(1, max_days + 1):
        print(f"  Día {k} (SL)...", end="")
        
        y_train = ((df_train['event_type'] == 'SL') & 
                   (df_train['time_to_event_days'] == k)).astype(int)
        
        mask_train = df_train['time_to_event_days'] >= k
        
        if mask_train.sum() < 10:
            print(f" SKIP (datos insuficientes)")
            continue
        
        X_train_k = df_train.loc[mask_train, feature_cols].fillna(0)
        y_train_k = y_train[mask_train]
        
        if y_train_k.sum() < 2:
            print(f" SKIP (sin eventos positivos)")
            continue
        
        clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=10,
            random_state=42,
            class_weight='balanced'
        )
        clf.fit(X_train_k, y_train_k)
        models_sl[k] = clf
        print(" OK")
    
    return models_tp, models_sl, feature_cols

def train_monte_carlo_calibration(df_train):
    """
    Calibra parámetros para Monte Carlo: mu y sigma condicionales a features.
    """
    print(f"\n[train_mc] Calibrando Monte Carlo...")
    
    # Para eventos TP, estimar mu y sigma
    df_tp = df_train[df_train['event_type'] == 'TP'].copy()
    
    if len(df_tp) < 10:
        print("[train_mc] WARN: Pocos eventos TP para calibrar MC")
        return None
    
    # mu ~ y_hat / time_to_event (retorno por día)
    df_tp['mu_realized'] = df_tp['abs_y_hat'] / df_tp['time_to_event_days']
    
    # sigma ~ atr_pct
    df_tp['sigma_realized'] = df_tp['atr_pct']
    
    # Entrenar regresores simples para mu y sigma
    feature_cols = ['abs_y_hat', 'atr_pct', 'prob_win', 'horizon_days']
    
    from sklearn.ensemble import RandomForestRegressor
    
    X_train = df_tp[feature_cols].fillna(0)
    
    # Modelo para mu
    mu_model = RandomForestRegressor(n_estimators=50, max_depth=3, random_state=42)
    mu_model.fit(X_train, df_tp['mu_realized'])
    
    # Modelo para sigma
    sigma_model = RandomForestRegressor(n_estimators=50, max_depth=3, random_state=42)
    sigma_model.fit(X_train, df_tp['sigma_realized'])
    
    print(f"[train_mc] mu_mean={df_tp['mu_realized'].mean():.4f}, "
          f"sigma_mean={df_tp['sigma_realized'].mean():.4f}")
    
    return {
        'mu_model': mu_model,
        'sigma_model': sigma_model,
        'feature_cols': feature_cols
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/trading/time_to_event_labeled.parquet")
    ap.add_argument("--output-dir", default="models")
    ap.add_argument("--max-days", type=int, default=5, help="Horizonte máximo para hazard discreto")
    ap.add_argument("--test-size", type=float, default=0.2)
    args = ap.parse_args()
    
    print(f"[train_tth] Cargando {args.input}...")
    
    if not os.path.exists(args.input):
        print(f"[train_tth] ERROR: {args.input} no existe. Ejecuta 37_label_time_to_event.py primero")
        return
    
    df = pd.read_parquet(args.input)
    print(f"[train_tth] {len(df)} registros cargados")
    
    # Split train/test
    df_train, df_test = train_test_split(df, test_size=args.test_size, random_state=42)
    print(f"[train_tth] Train: {len(df_train)}, Test: {len(df_test)}")
    
    # 1. Hazard discreto
    models_tp, models_sl, feature_cols = train_hazard_discrete(
        df_train, df_test, max_days=args.max_days
    )
    
    # 2. Monte Carlo calibration
    mc_calib = train_monte_carlo_calibration(df_train)
    
    # Guardar modelos
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Hazard discreto
    hazard_bundle = {
        'models_tp': models_tp,
        'models_sl': models_sl,
        'feature_cols': feature_cols,
        'max_days': args.max_days
    }
    hazard_path = os.path.join(args.output_dir, 'tth_hazard_discrete.joblib')
    joblib.dump(hazard_bundle, hazard_path)
    print(f"\n[train_tth] Hazard discreto → {hazard_path}")
    
    # Monte Carlo
    if mc_calib:
        mc_path = os.path.join(args.output_dir, 'tth_monte_carlo.joblib')
        joblib.dump(mc_calib, mc_path)
        print(f"[train_tth] Monte Carlo → {mc_path}")
    
    # Metadata
    metadata = {
        'train_records': len(df_train),
        'test_records': len(df_test),
        'max_days': args.max_days,
        'feature_cols': feature_cols,
        'tp_models_trained': len(models_tp),
        'sl_models_trained': len(models_sl),
        'mc_calibrated': mc_calib is not None
    }
    
    meta_path = os.path.join(args.output_dir, 'tth_metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"[train_tth] Metadata → {meta_path}")
    print("\n[train_tth] ✓ Entrenamiento completado")

if __name__ == "__main__":
    main()
