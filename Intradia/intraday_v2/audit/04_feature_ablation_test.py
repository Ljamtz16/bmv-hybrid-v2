# Audit Test 4: Feature Ablation Test
# Remove strongest features one-by-one and test impact on AUC/Brier
# If removing top feature does NOT reduce AUC > 5% → suspicious
#
# Output: artifacts/audit/feature_ablation.csv

import pandas as pd
import numpy as np
from pathlib import Path
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


def feature_ablation_test():
    """
    Remove top features one-by-one and measure performance drop.
    """
    print("[AUDIT-04] === FEATURE ABLATION TEST ===\n")
    
    # === Load dataset ===
    dataset_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    df = pd.read_parquet(dataset_path)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    
    # === Add categorical features to full df ===
    df['side_numeric'] = (df['side'] == 'BUY').astype(int)
    df['window_OPEN'] = (df['window'] == 'OPEN').astype(int)
    df['window_CLOSE'] = (df['window'] == 'CLOSE').astype(int)
    
    all_features = [
        'atr14', 'ema20', 'daily_range_pct', 'is_high_vol', 'is_wide_range', 'is_directional',
        'window_range', 'window_return', 'window_body', 'w_close_vs_ema',
        'range_to_atr', 'body_to_atr', 'n_bars',
        'gap_atr', 'overnight_ret', 'rvol', 'vwap_dist',
        'body_to_atr_x_high_vol', 'range_to_atr_x_directional',
        'side_numeric', 'window_OPEN', 'window_CLOSE'
    ]
    
    # === Setup temporal split ===
    train_end = pd.Timestamp('2025-06-30')
    test_start = pd.Timestamp('2025-07-01')
    
    df_train = df[df['date'] <= train_end].copy()
    df_test = df[df['date'] >= test_start].copy()
    
    X_train = df_train[all_features].copy()
    y_train = df_train['y'].copy()
    X_test = df_test[all_features].copy()
    y_test = df_test['y'].copy()
    
    train_valid = ~(X_train.isna().any(axis=1) | y_train.isna())
    test_valid = ~(X_test.isna().any(axis=1) | y_test.isna())
    
    X_train = X_train[train_valid]
    y_train = y_train[train_valid]
    X_test = X_test[test_valid]
    y_test = y_test[test_valid]
    
    print(f"[AUDIT-04] Train: {len(X_train):,} | Test: {len(X_test):,}\n")
    
    # === Baseline (all features) ===
    print("[AUDIT-04] Training baseline model (all features)...")
    
    pipeline_baseline = Pipeline([
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
    ])
    
    lambda_decay = 0.001
    max_date = df_train['date'].max()
    age_days = (max_date - df_train['date']).dt.days
    sample_weights = np.exp(-lambda_decay * age_days)
    sample_weights = sample_weights[train_valid]
    
    pipeline_baseline.fit(X_train, y_train, model__sample_weight=sample_weights)
    
    # Calibrate
    n_cal = int(len(X_train) * 0.5)
    X_cal, X_val_cal = X_train[:n_cal], X_train[n_cal:]
    y_cal, y_val_cal = y_train[:n_cal], y_train[n_cal:]
    
    calibrator_baseline = CalibratedClassifierCV(estimator=pipeline_baseline, method='isotonic', cv='prefit')
    calibrator_baseline.fit(X_val_cal, y_val_cal)
    
    y_test_proba_baseline = calibrator_baseline.predict_proba(X_test)[:, 1]
    auc_baseline = roc_auc_score(y_test, y_test_proba_baseline)
    brier_baseline = brier_score_loss(y_test, y_test_proba_baseline)
    ece_baseline = _ece(y_test.values, y_test_proba_baseline)
    
    print(f"[AUDIT-04] Baseline AUC: {auc_baseline:.4f} | Brier: {brier_baseline:.4f} | ECE: {ece_baseline:.4f}\n")
    
    # === Features to ablate (top 4 by magnitude) ===
    ablation_features = [
        'window_return',  # +7.568
        'vwap_dist',      # -0.583
        'overnight_ret',  # +0.310
        'body_to_atr'     # +0.522
    ]
    
    ablation_results = []
    
    for feature_to_remove in ablation_features:
        print(f"[AUDIT-04] Ablating: {feature_to_remove}")
        
        features_remaining = [f for f in all_features if f != feature_to_remove]
        
        X_train_abl = X_train[features_remaining].copy()
        X_test_abl = X_test[features_remaining].copy()
        
        # Train ablated model
        pipeline_abl = Pipeline([
            ('scaler', StandardScaler()),
            ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
        ])
        
        pipeline_abl.fit(X_train_abl, y_train, model__sample_weight=sample_weights)
        
        # Calibrate
        X_cal_abl = X_cal[features_remaining].copy()
        X_val_cal_abl = X_val_cal[features_remaining].copy()
        
        calibrator_abl = CalibratedClassifierCV(estimator=pipeline_abl, method='isotonic', cv='prefit')
        calibrator_abl.fit(X_val_cal_abl, y_val_cal)
        
        y_test_proba_abl = calibrator_abl.predict_proba(X_test_abl)[:, 1]
        auc_abl = roc_auc_score(y_test, y_test_proba_abl)
        brier_abl = brier_score_loss(y_test, y_test_proba_abl)
        ece_abl = _ece(y_test.values, y_test_proba_abl)
        
        # Compute % change
        auc_pct_drop = (auc_baseline - auc_abl) / auc_baseline * 100
        brier_pct_change = (brier_abl - brier_baseline) / brier_baseline * 100
        
        print(f"[AUDIT-04]   AUC: {auc_abl:.4f} (drop {auc_pct_drop:.1f}%) | Brier: {brier_abl:.4f} (Δ {brier_pct_change:+.1f}%)")
        
        ablation_results.append({
            'feature_removed': feature_to_remove,
            'auc_with_feature': float(auc_baseline),
            'auc_without_feature': float(auc_abl),
            'auc_drop_pct': float(auc_pct_drop),
            'brier_without_feature': float(brier_abl),
            'brier_change_pct': float(brier_pct_change),
            'ece_without_feature': float(ece_abl)
        })
    
    # === Summary ===
    print(f"\n[AUDIT-04] === ABLATION SUMMARY ===")
    
    avg_auc_drop = np.mean([r['auc_drop_pct'] for r in ablation_results])
    min_auc_drop = np.min([r['auc_drop_pct'] for r in ablation_results])
    
    print(f"[AUDIT-04] Average AUC drop: {avg_auc_drop:.1f}%")
    print(f"[AUDIT-04] Min AUC drop: {min_auc_drop:.1f}%")
    
    # Verdict
    if min_auc_drop < 5:
        print(f"[AUDIT-04] ⚠️ WARNING: Removing top features has minimal impact")
        verdict = 'YELLOW'
    else:
        print(f"[AUDIT-04] ✅ PASS: Features are meaningful")
        verdict = 'GREEN'
    
    print(f"[AUDIT-04] Verdict: {verdict}")
    
    # === Save results ===
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df_ablation = pd.DataFrame(ablation_results)
    df_ablation.to_csv(output_dir / 'feature_ablation.csv', index=False)
    print(f"\n[AUDIT-04] ✅ Results saved to feature_ablation.csv")
    
    return {
        'results': ablation_results,
        'average_auc_drop_pct': float(avg_auc_drop),
        'min_auc_drop_pct': float(min_auc_drop),
        'verdict': verdict
    }


if __name__ == '__main__':
    results = feature_ablation_test()
