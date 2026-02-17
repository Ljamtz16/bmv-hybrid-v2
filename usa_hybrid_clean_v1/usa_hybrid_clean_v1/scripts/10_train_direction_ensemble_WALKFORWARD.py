# Script: 10_train_direction_ensemble_WALKFORWARD.py
# Entrena ensemble con WALK-FORWARD VALIDATION (sin leakage)
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, brier_score_loss
import joblib
import os

FEATURES_PATH = 'data/daily/features_enhanced_binary_targets.parquet'
TARGET_COL = 'target_binary'
MODEL_DIR = 'models/direction/'
VAL_DIR = 'val/'

def train_ensemble_walkforward():
    """
    Walk-forward validation con TimeSeriesSplit
    - Train en ventanas pasadas
    - Test en ventana futura
    - Sin contamination entre splits
    """
    print("[INFO] Cargando datos...")
    df = pd.read_parquet(FEATURES_PATH)
    df = df.dropna(subset=[TARGET_COL])
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Features mejoradas (excluir columns auxiliares)
    exclude_cols = ['timestamp', 'ticker', TARGET_COL, 'target', 'target_ordinal', 'open', 'high', 'low', 'close', 'volume',
                    'close_fwd', 'ret_fwd', 'thr_up', 'thr_dn', 'atr_pct_w', 'k', 'regime',
                    'prev_close', 'hh_20', 'll_20', 'hh_60', 'll_60',
                    'vol_avg_20', 'is_up', 'dow', 'day_of_month']
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # Remover features con muchos NaN
    feature_cols = [c for c in feature_cols if df[c].notna().sum() > len(df) * 0.8]
    
    print(f"[INFO] Features seleccionadas: {len(feature_cols)}")
    print(f"[INFO] Features: {', '.join(feature_cols[:10])}...")
    
    df_clean = df.dropna(subset=feature_cols)
    X = df_clean[feature_cols].values
    y = df_clean[TARGET_COL].values
    timestamps = df_clean['timestamp'].values
    
    print(f"[INFO] Dataset cleaned: {len(X)} samples")
    print(f"[INFO] Date range: {df_clean['timestamp'].min()} to {df_clean['timestamp'].max()}")
    
    # Walk-forward con 5 folds
    tscv = TimeSeriesSplit(n_splits=5)
    
    fold_results = []
    all_predictions = []
    
    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X)):
        print(f"\n{'='*60}")
        print(f"FOLD {fold_idx + 1}/5")
        print(f"{'='*60}")
        
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        train_dates = pd.to_datetime(timestamps[train_idx])
        test_dates = pd.to_datetime(timestamps[test_idx])
        
        print(f"Train: {len(X_train)} samples | {train_dates.min()} to {train_dates.max()}")
        print(f"Test:  {len(X_test)} samples  | {test_dates.min()} to {test_dates.max()}")
        
        # Entrenar modelos base
        print("[INFO] Entrenando modelos base...")
        rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        xgb = XGBClassifier(n_estimators=100, random_state=42, use_label_encoder=False, eval_metric='logloss')
        cat = CatBoostClassifier(iterations=100, verbose=0, random_state=42)
        
        rf.fit(X_train, y_train)
        xgb.fit(X_train, y_train)
        cat.fit(X_train, y_train)
        
        # Predicciones en test
        rf_pred_test = rf.predict_proba(X_test)[:, 1].reshape(-1, 1)
        xgb_pred_test = xgb.predict_proba(X_test)[:, 1].reshape(-1, 1)
        cat_pred_test = cat.predict_proba(X_test)[:, 1].reshape(-1, 1)
        X_meta_test = np.hstack([rf_pred_test, xgb_pred_test, cat_pred_test])
        
        # Entrenar meta-learner en train
        rf_pred_train = rf.predict_proba(X_train)[:, 1].reshape(-1, 1)
        xgb_pred_train = xgb.predict_proba(X_train)[:, 1].reshape(-1, 1)
        cat_pred_train = cat.predict_proba(X_train)[:, 1].reshape(-1, 1)
        X_meta_train = np.hstack([rf_pred_train, xgb_pred_train, cat_pred_train])
        
        meta = LogisticRegression(max_iter=1000, random_state=42)
        meta.fit(X_meta_train, y_train)
        
        # Predecir en test con meta
        prob_pred = meta.predict_proba(X_meta_test)[:, 1]
        
        # Métricas OOS
        auc = roc_auc_score(y_test, prob_pred)
        brier = brier_score_loss(y_test, prob_pred)
        
        print(f"\n[RESULTS] Fold {fold_idx + 1}:")
        print(f"  AUC:   {auc:.4f}")
        print(f"  Brier: {brier:.4f}")
        
        fold_results.append({
            'fold': fold_idx + 1,
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'train_start': train_dates.min(),
            'train_end': train_dates.max(),
            'test_start': test_dates.min(),
            'test_end': test_dates.max(),
            'auc': auc,
            'brier': brier,
            'target_mean': y_test.mean()
        })
        
        # Guardar predicciones OOS
        for i, idx in enumerate(test_idx):
            all_predictions.append({
                'fold': fold_idx + 1,
                'idx': idx,
                'timestamp': timestamps[idx],
                'ticker': df.loc[idx, 'ticker'],
                'y_true': y_test[i],
                'prob_pred': prob_pred[i]
            })
    
    # Resumen global
    print(f"\n{'='*60}")
    print("RESUMEN WALK-FORWARD VALIDATION")
    print(f"{'='*60}")
    
    fold_df = pd.DataFrame(fold_results)
    print("\n", fold_df.to_string(index=False))
    
    avg_auc = fold_df['auc'].mean()
    avg_brier = fold_df['brier'].mean()
    
    print(f"\n📊 Métricas Promedio (OOS):")
    print(f"  AUC:   {avg_auc:.4f} ± {fold_df['auc'].std():.4f}")
    print(f"  Brier: {avg_brier:.4f} ± {fold_df['brier'].std():.4f}")
    
    # Guardar resultados
    os.makedirs(VAL_DIR, exist_ok=True)
    fold_df.to_csv(VAL_DIR + 'walkforward_results.csv', index=False)
    
    pred_df = pd.DataFrame(all_predictions)
    pred_df.to_parquet(VAL_DIR + 'oos_predictions.parquet', index=False)
    
    print(f"\n[OK] Resultados guardados en {VAL_DIR}")
    
    # Re-entrenar en TODO el dataset para producción
    print(f"\n{'='*60}")
    print("RE-ENTRENAMIENTO EN DATASET COMPLETO (PRODUCCIÓN)")
    print(f"{'='*60}")
    
    print("[INFO] Entrenando modelos finales...")
    rf_final = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    xgb_final = XGBClassifier(n_estimators=100, random_state=42, use_label_encoder=False, eval_metric='logloss')
    cat_final = CatBoostClassifier(iterations=100, verbose=0, random_state=42)
    
    rf_final.fit(X, y)
    xgb_final.fit(X, y)
    cat_final.fit(X, y)
    
    # Meta-learner final
    rf_pred_all = rf_final.predict_proba(X)[:, 1].reshape(-1, 1)
    xgb_pred_all = xgb_final.predict_proba(X)[:, 1].reshape(-1, 1)
    cat_pred_all = cat_final.predict_proba(X)[:, 1].reshape(-1, 1)
    X_meta_all = np.hstack([rf_pred_all, xgb_pred_all, cat_pred_all])
    
    meta_final = LogisticRegression(max_iter=1000, random_state=42)
    meta_final.fit(X_meta_all, y)
    
    # Guardar modelos
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(rf_final, MODEL_DIR + 'rf.joblib')
    joblib.dump(xgb_final, MODEL_DIR + 'xgb.joblib')
    joblib.dump(cat_final, MODEL_DIR + 'cat.joblib')
    joblib.dump(meta_final, MODEL_DIR + 'meta.joblib')
    
    print(f"[OK] Modelos finales guardados en {MODEL_DIR}")
    
    return avg_auc, avg_brier

if __name__ == "__main__":
    auc, brier = train_ensemble_walkforward()
    
    print(f"\n{'='*60}")
    print("VALIDACIÓN COMPLETADA")
    print(f"{'='*60}")
    print(f"\n✅ AUC OOS:   {auc:.4f}")
    print(f"✅ Brier OOS: {brier:.4f}")
    
    if auc > 0.60 and brier < 0.20:
        print("\n✅ MODELO APTO PARA PRODUCCIÓN")
    else:
        print("\n⚠️  REVISAR: Métricas por debajo de targets")
