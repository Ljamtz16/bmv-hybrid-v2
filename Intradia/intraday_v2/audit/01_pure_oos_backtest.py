# Audit Test 1: Pure Out-of-Sample Backtest
# Train ONLY on 2020-2025-06-30, Test ONLY on 2025-07-01 to 2026-02-13
# NO refitting during test period
#
# Output: artifacts/audit/pure_oos_metrics.json

import pandas as pd
import numpy as np
import json
import joblib
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss, average_precision_score
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


def pure_oos_backtest():
    """
    Train on fixed period, test on disjoint OOS period without refitting.
    """
    print("[AUDIT-01] === PURE OUT-OF-SAMPLE BACKTEST ===\n")
    
    # === Load dataset ===
    dataset_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    print(f"[AUDIT-01] Loading dataset from {dataset_path}...")
    df = pd.read_parquet(dataset_path)
    
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    
    # === Fixed split (NO refitting during test) ===
    train_end = pd.Timestamp('2025-06-30')
    test_start = pd.Timestamp('2025-07-01')
    
    # === Add categorical features to full df ===
    df['side_numeric'] = (df['side'] == 'BUY').astype(int)
    df['window_OPEN'] = (df['window'] == 'OPEN').astype(int)
    df['window_CLOSE'] = (df['window'] == 'CLOSE').astype(int)
    
    df_train = df[df['date'] <= train_end].copy()
    df_test = df[df['date'] >= test_start].copy()
    
    print(f"[AUDIT-01] Train period: {df_train['date'].min()} to {df_train['date'].max()} | {len(df_train):,} samples")
    print(f"[AUDIT-01] Test period:  {df_test['date'].min()} to {df_test['date'].max()} | {len(df_test):,} samples\n")
    
    if len(df_train) == 0 or len(df_test) == 0:
        raise ValueError("Train or test split is empty!")
    
    # === Feature list ===
    feature_cols = [
        'atr14', 'ema20', 'daily_range_pct', 'is_high_vol', 'is_wide_range', 'is_directional',
        'window_range', 'window_return', 'window_body', 'w_close_vs_ema',
        'range_to_atr', 'body_to_atr', 'n_bars',
        'gap_atr', 'overnight_ret', 'rvol', 'vwap_dist',
        'body_to_atr_x_high_vol', 'range_to_atr_x_directional',
        'side_numeric', 'window_OPEN', 'window_CLOSE'
    ]
    
    # === Prepare data ===
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
    
    print(f"[AUDIT-01] After NaN drop: Train {len(X_train):,} | Test {len(X_test):,}")
    
    # Add categorical features
    X_train['side_numeric'] = (df_train['side'] == 'BUY').astype(int).values
    X_train['window_OPEN'] = (df_train['window'] == 'OPEN').astype(int).values
    X_train['window_CLOSE'] = (df_train['window'] == 'CLOSE').astype(int).values
    
    X_test['side_numeric'] = (df_test['side'] == 'BUY').astype(int).values
    X_test['window_OPEN'] = (df_test['window'] == 'OPEN').astype(int).values
    X_test['window_CLOSE'] = (df_test['window'] == 'CLOSE').astype(int).values
    
    # === Train model (ONE TIME, no refitting) ===
    print(f"\n[AUDIT-01] Training model on fixed train set...")
    
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
    ])
    
    lambda_decay = 0.001
    max_date = df_train['date'].max()
    age_days_train = (max_date - df_train['date']).dt.days
    sample_weights_train = np.exp(-lambda_decay * age_days_train)
    sample_weights_train = sample_weights_train[train_valid]
    
    pipeline.fit(X_train, y_train, model__sample_weight=sample_weights_train)
    
    # === Calibrate on train set (within fold) ===
    print(f"[AUDIT-01] Calibrating on train set...")
    calibrator = CalibratedClassifierCV(estimator=pipeline, method='isotonic', cv='prefit')
    
    y_train_proba_raw = pipeline.predict_proba(X_train)[:, 1]
    
    # Split train into calibration and validation for fitting calibrator
    n_cal = int(len(X_train) * 0.5)
    X_cal, X_val_for_cal = X_train[:n_cal], X_train[n_cal:]
    y_cal, y_val_for_cal = y_train[:n_cal], y_train[n_cal:]
    
    calibrator.fit(X_val_for_cal, y_val_for_cal)
    
    # === Evaluate on TEST set (pure OOS) ===
    print(f"\n[AUDIT-01] Evaluating on pure OOS test set (no refitting)...")
    
    y_test_proba_raw = pipeline.predict_proba(X_test)[:, 1]
    y_test_proba_cal = calibrator.predict_proba(X_test)[:, 1]
    
    # Raw metrics
    auc_test_raw = roc_auc_score(y_test, y_test_proba_raw)
    brier_test_raw = brier_score_loss(y_test, y_test_proba_raw)
    ap_test_raw = average_precision_score(y_test, y_test_proba_raw)
    
    # Calibrated metrics
    auc_test_cal = roc_auc_score(y_test, y_test_proba_cal)
    brier_test_cal = brier_score_loss(y_test, y_test_proba_cal)
    ap_test_cal = average_precision_score(y_test, y_test_proba_cal)
    
    ece_test_cal = _ece(y_test.values, y_test_proba_cal)
    
    print(f"[AUDIT-01] === PURE OOS RESULTS ===")
    print(f"[AUDIT-01] AUC (raw): {auc_test_raw:.4f}")
    print(f"[AUDIT-01] AUC (calibrated): {auc_test_cal:.4f}")
    print(f"[AUDIT-01] Brier (raw): {brier_test_raw:.4f}")
    print(f"[AUDIT-01] Brier (calibrated): {brier_test_cal:.4f}")
    print(f"[AUDIT-01] AP (calibrated): {ap_test_cal:.4f}")
    print(f"[AUDIT-01] ECE (calibrated): {ece_test_cal:.4f}")
    
    # === Backtest metrics ===
    # Load plan and execute backtest on OOS test period
    print(f"\n[AUDIT-01] Running OOS backtest...")
    
    plan_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan_clean.csv'
    bars_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet'
    
    plan = pd.read_csv(plan_path)
    plan['date'] = pd.to_datetime(plan['date'], utc=True).dt.tz_localize(None)
    
    # Filter plan to OOS period only
    plan_oos = plan[plan['date'] >= test_start].copy()
    print(f"[AUDIT-01] Plan trades in OOS period: {len(plan_oos):,}")
    
    if len(plan_oos) > 0:
        # Execute backtest on OOS trades
        bars = pd.read_parquet(bars_path)
        # Normalize timestamp to tz-naive for comparison
        if hasattr(bars['timestamp'].dtype, 'tz') and bars['timestamp'].dtype.tz is not None:
            bars['timestamp'] = bars['timestamp'].dt.tz_localize(None)
        
        pnl_total = 0.0
        trades_valid = 0
        trades_tp = 0
        
        for row in plan_oos.itertuples(index=False):
            ticker = row.ticker
            entry_price = row.entry_price
            tp = row.tp_price
            sl = row.sl_price
            
            ticker_bars = bars[bars['ticker'] == ticker].sort_values('timestamp')
            entry_time = pd.to_datetime(row.entry_time, utc=True).tz_localize(None)
            
            future = ticker_bars[ticker_bars['timestamp'] > entry_time].head(16)
            
            if future.empty:
                continue
            
            hit_tp = (future['high'] >= tp).any()
            hit_sl = (future['low'] <= sl).any()
            
            if hit_sl and hit_tp:
                pnl = sl - entry_price
                trades_valid += 1
            elif hit_tp:
                pnl = tp - entry_price
                trades_valid += 1
                trades_tp += 1
            elif hit_sl:
                pnl = sl - entry_price
                trades_valid += 1
            else:
                continue
            
            pnl_total += pnl
        
        if trades_valid > 0:
            wr_oos = trades_tp / trades_valid * 100
            pf_oos = pnl_total / abs(pnl_total - trades_tp * 0.5) if trades_valid > trades_tp else 1.0
        else:
            wr_oos = 0
            pf_oos = 0
        
        print(f"[AUDIT-01] OOS Backtest: {trades_valid} valid trades, WR {wr_oos:.1f}%, Total PnL ${pnl_total:.2f}")
    else:
        wr_oos = np.nan
        pf_oos = np.nan
        pnl_total = np.nan
        trades_valid = 0
    
    # === Save results ===
    results = {
        'period': {
            'train_start': str(df_train['date'].min()),
            'train_end': str(df_train['date'].max()),
            'test_start': str(df_test['date'].min()),
            'test_end': str(df_test['date'].max()),
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        },
        'metrics': {
            'auc_raw': float(auc_test_raw),
            'auc_calibrated': float(auc_test_cal),
            'brier_raw': float(brier_test_raw),
            'brier_calibrated': float(brier_test_cal),
            'ap_calibrated': float(ap_test_cal),
            'ece_calibrated': float(ece_test_cal)
        },
        'backtest': {
            'trades': trades_valid,
            'wr_percent': float(wr_oos) if not np.isnan(wr_oos) else None,
            'pf': float(pf_oos) if not np.isnan(pf_oos) else None,
            'pnl': float(pnl_total) if not np.isnan(pnl_total) else None
        },
        'verdict': 'GREEN' if auc_test_cal > 0.75 and not np.isnan(wr_oos) and wr_oos > 60 else 'YELLOW'
    }
    
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / 'pure_oos_metrics.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n[AUDIT-01] ✅ Results saved to {output_path}")
    print(f"[AUDIT-01] Verdict: {results['verdict']}")
    
    return results


if __name__ == '__main__':
    results = pure_oos_backtest()
