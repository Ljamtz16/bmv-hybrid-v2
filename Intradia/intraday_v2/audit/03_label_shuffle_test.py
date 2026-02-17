# Audit Test 3: Label Shuffle Test
# Detect hidden leakage by shuffling labels and training
# If shuffled model achieves PF > 1.5 → CRITICAL LEAKAGE ALERT
#
# Output: artifacts/audit/shuffle_results.csv

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score
from sklearn.calibration import CalibratedClassifierCV


def label_shuffle_test(n_iterations=10):
    """
    Shuffle labels randomly, train model, evaluate AUC.
    Expected: AUC ≈ 0.5 (random)
    If AUC > 0.7 consistently → LEAKAGE DETECTED
    """
    print("[AUDIT-03] === LABEL SHUFFLE TEST ===\n")
    print(f"[AUDIT-03] Running {n_iterations} label shuffle iterations...\n")
    
    # === Load dataset ===
    dataset_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    df = pd.read_parquet(dataset_path)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    
    # === Add categorical features to full df ===
    df['side_numeric'] = (df['side'] == 'BUY').astype(int)
    df['window_OPEN'] = (df['window'] == 'OPEN').astype(int)
    df['window_CLOSE'] = (df['window'] == 'CLOSE').astype(int)
    
    feature_cols = [
        'atr14', 'ema20', 'daily_range_pct', 'is_high_vol', 'is_wide_range', 'is_directional',
        'window_range', 'window_return', 'window_body', 'w_close_vs_ema',
        'range_to_atr', 'body_to_atr', 'n_bars',
        'gap_atr', 'overnight_ret', 'rvol', 'vwap_dist',
        'body_to_atr_x_high_vol', 'range_to_atr_x_directional',
        'side_numeric', 'window_OPEN', 'window_CLOSE'
    ]
    
    # === Use temporal split ===
    train_end = pd.Timestamp('2025-06-30')
    test_start = pd.Timestamp('2025-07-01')
    
    df_train = df[df['date'] <= train_end].copy()
    df_test = df[df['date'] >= test_start].copy()
    
    X_train = df_train[feature_cols].copy()
    y_train = df_train['y'].copy()
    X_test = df_test[feature_cols].copy()
    y_test = df_test['y'].copy()
    
    # Drop NaN
    train_valid = ~(X_train.isna().any(axis=1) | y_train.isna())
    test_valid = ~(X_test.isna().any(axis=1) | y_test.isna())
    
    X_train = X_train[train_valid]
    y_train = y_train[train_valid]
    X_test = X_test[test_valid]
    y_test = y_test[test_valid]
    
    print(f"[AUDIT-03] Train: {len(X_train):,} samples, Test: {len(X_test):,} samples\n")
    
    results = []
    
    for iteration in range(n_iterations):
        # === SHUFFLE labels ===
        y_train_shuffled = y_train.sample(frac=1, random_state=iteration).values
        y_train_shuffled = pd.Series(y_train_shuffled, index=y_train.index)
        
        # Train
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
        ])
        
        try:
            pipeline.fit(X_train, y_train_shuffled)
            
            # Evaluate on REAL (unshuffled) test labels
            y_test_proba = pipeline.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, y_test_proba)
            
            print(f"[AUDIT-03] Iteration {iteration+1}: AUC (shuffled labels) = {auc:.4f}")
            
            results.append({
                'iteration': iteration + 1,
                'auc': float(auc),
                'y_train_shuffled': True
            })
        except Exception as e:
            print(f"[AUDIT-03] Iteration {iteration+1}: FAILED - {e}")
            results.append({
                'iteration': iteration + 1,
                'auc': np.nan,
                'y_train_shuffled': True
            })
    
    # === Analyze results ===
    df_results = pd.DataFrame(results)
    df_results_clean = df_results.dropna(subset=['auc'])
    
    mean_auc = df_results_clean['auc'].mean()
    max_auc = df_results_clean['auc'].max()
    pct_auc_gt_70 = (df_results_clean['auc'] > 0.70).sum() / len(df_results_clean) * 100
    
    print(f"\n[AUDIT-03] === SHUFFLE TEST RESULTS ===")
    print(f"[AUDIT-03] Mean AUC (shuffled labels): {mean_auc:.4f}")
    print(f"[AUDIT-03] Max AUC (shuffled labels): {max_auc:.4f}")
    print(f"[AUDIT-03] % of runs with AUC > 0.70: {pct_auc_gt_70:.1f}%")
    
    # === Verdict ===
    if pct_auc_gt_70 > 30:
        print(f"\n[AUDIT-03] ⚠️ CRITICAL LEAKAGE ALERT: Shuffled labels achieved high AUC!")
        verdict = 'RED'
    elif mean_auc > 0.55:
        print(f"\n[AUDIT-03] ⚠️ WARNING: Shuffled labels show above-random performance")
        verdict = 'YELLOW'
    else:
        print(f"\n[AUDIT-03] ✅ PASS: Shuffled labels show random performance (AUC ≈ 0.5)")
        verdict = 'GREEN'
    
    print(f"[AUDIT-03] Verdict: {verdict}")
    
    # === Save results ===
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df_results.to_csv(output_dir / 'shuffle_results.csv', index=False)
    print(f"\n[AUDIT-03] ✅ Results saved to shuffle_results.csv")
    
    return {
        'mean_auc': float(mean_auc),
        'max_auc': float(max_auc),
        'pct_auc_gt_70': float(pct_auc_gt_70),
        'verdict': verdict
    }


if __name__ == '__main__':
    results = label_shuffle_test(n_iterations=10)
