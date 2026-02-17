# Audit Test 2: Rolling Walk-Forward Validation
# Train 2 years, test next 3 months, step forward 3 months
#
# Output: artifacts/audit/walkforward_results.csv
#         artifacts/audit/walkforward_summary.json

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import timedelta
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV


def _ece(y_true, y_pred, n_bins=10):
    """Expected Calibration Error"""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        in_bin = (y_pred >= bin_edges[i]) & (y_pred < bin_edges[i + 1])
        if in_bin.sum() == 0:
            continue
        acc = y_true[in_bin].mean()
        conf = y_pred[in_bin].mean()
        ece += in_bin.sum() / len(y_true) * abs(acc - conf)
    return ece


def walkforward_validation():
    """
    Rolling walk-forward: 2y train → 3m test, step 3m
    """
    print("[AUDIT-02] === ROLLING WALK-FORWARD VALIDATION ===\n")
    
    # === Load dataset ===
    dataset_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    print(f"[AUDIT-02] Loading dataset...")
    df = pd.read_parquet(dataset_path)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    
    min_date = df['date'].min()
    max_date = df['date'].max()
    print(f"[AUDIT-02] Date range: {min_date} to {max_date}")
    
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
    
    # === Define rolling windows ===
    train_window_days = 365 * 2  # 2 years
    test_window_days = 90  # 3 months
    step_days = 90  # step 3 months
    
    folds = []
    test_start = min_date + timedelta(days=train_window_days)
    fold_num = 0
    
    print(f"\n[AUDIT-02] Generating folds (2y train, 3m test, 3m step)...\n")
    
    while test_start + timedelta(days=test_window_days) <= max_date:
        train_start = test_start - timedelta(days=train_window_days)
        test_end = test_start + timedelta(days=test_window_days)
        
        df_train = df[(df['date'] >= train_start) & (df['date'] < test_start)].copy()
        df_test = df[(df['date'] >= test_start) & (df['date'] < test_end)].copy()
        
        print(f"[AUDIT-02] Fold {fold_num}: Train {train_start.date()} → {test_start.date()} ({len(df_train)} samples) | Test {test_start.date()} → {test_end.date()} ({len(df_test)} samples)")
        
        if len(df_train) < 100 or len(df_test) < 10:
            print(f"[AUDIT-02]   ⚠️ Insufficient samples, skipping fold")
            test_start += timedelta(days=step_days)
            continue
        
        # === Train and evaluate ===
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
        
        # Train
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
        ])
        
        lambda_decay = 0.001
        max_train_date = df_train['date'].max()
        age_days = (max_train_date - df_train['date']).dt.days
        sample_weights = np.exp(-lambda_decay * age_days)
        sample_weights = sample_weights[train_valid]
        
        pipeline.fit(X_train, y_train, model__sample_weight=sample_weights)
        
        # Calibrate
        n_cal = int(len(X_train) * 0.5)
        X_cal, X_val_for_cal = X_train[:n_cal], X_train[n_cal:]
        y_cal, y_val_for_cal = y_train[:n_cal], y_train[n_cal:]
        
        calibrator = CalibratedClassifierCV(estimator=pipeline, method='isotonic', cv='prefit')
        calibrator.fit(X_val_for_cal, y_val_for_cal)
        
        # Evaluate
        y_test_proba = calibrator.predict_proba(X_test)[:, 1]
        
        auc = roc_auc_score(y_test, y_test_proba)
        brier = brier_score_loss(y_test, y_test_proba)
        ece = _ece(y_test.values, y_test_proba)
        
        print(f"[AUDIT-02]   AUC: {auc:.4f} | Brier: {brier:.4f} | ECE: {ece:.4f}")
        
        folds.append({
            'fold': fold_num,
            'train_start': str(train_start.date()),
            'train_end': str(test_start.date()),
            'test_start': str(test_start.date()),
            'test_end': str(test_end.date()),
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'auc': float(auc),
            'brier': float(brier),
            'ece': float(ece)
        })
        
        test_start += timedelta(days=step_days)
    
    # === Save fold results ===
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df_folds = pd.DataFrame(folds)
    df_folds.to_csv(output_dir / 'walkforward_results.csv', index=False)
    print(f"\n[AUDIT-02] ✅ Fold results saved")
    
    # === Summary statistics ===
    auc_mean = df_folds['auc'].mean()
    auc_std = df_folds['auc'].std()
    auc_min = df_folds['auc'].min()
    auc_max = df_folds['auc'].max()
    
    brier_mean = df_folds['brier'].mean()
    brier_std = df_folds['brier'].std()
    
    ece_mean = df_folds['ece'].mean()
    
    print(f"\n[AUDIT-02] === WALK-FORWARD SUMMARY ===")
    print(f"[AUDIT-02] Folds completed: {len(folds)}")
    print(f"[AUDIT-02] AUC: mean={auc_mean:.4f}, std={auc_std:.4f}, range=[{auc_min:.4f}, {auc_max:.4f}]")
    print(f"[AUDIT-02] Brier: mean={brier_mean:.4f}, std={brier_std:.4f}")
    print(f"[AUDIT-02] ECE: mean={ece_mean:.4f}")
    
    # Estimate stability: % of folds with AUC > 0.75
    stable_folds_pct = (df_folds['auc'] > 0.75).sum() / len(df_folds) * 100
    print(f"[AUDIT-02] Folds with AUC > 0.75: {stable_folds_pct:.1f}%")
    
    summary = {
        'total_folds': len(folds),
        'auc': {
            'mean': float(auc_mean),
            'std': float(auc_std),
            'min': float(auc_min),
            'max': float(auc_max)
        },
        'brier': {
            'mean': float(brier_mean),
            'std': float(brier_std)
        },
        'ece': {
            'mean': float(ece_mean)
        },
        'stability_metrics': {
            'pct_folds_auc_gt_075': float(stable_folds_pct),
            'verdict': 'GREEN' if stable_folds_pct >= 60 else 'YELLOW'
        }
    }
    
    with open(output_dir / 'walkforward_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"[AUDIT-02] Verdict: {summary['stability_metrics']['verdict']}")
    print(f"[AUDIT-02] ✅ Summary saved to walkforward_summary.json")
    
    return summary


if __name__ == '__main__':
    summary = walkforward_validation()
