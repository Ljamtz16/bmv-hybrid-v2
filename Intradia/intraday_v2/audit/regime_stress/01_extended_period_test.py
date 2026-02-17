# Regime Stress Test 1: Extended Historical Period 2015–2020
# Scenario A: Frozen model (train 2020–2025) -> test 2015–2020
# Scenario B: Refit model (train 2013–2015) -> test 2015–2020

import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.calibration import CalibratedClassifierCV

DATASET_PATH = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
TRADES_PATH = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
OUTPUT_DIR = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\regime_stress')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    'atr14', 'ema20', 'daily_range_pct', 'is_high_vol', 'is_wide_range', 'is_directional',
    'window_range', 'window_return', 'window_body', 'w_close_vs_ema',
    'range_to_atr', 'body_to_atr', 'n_bars',
    'gap_atr', 'overnight_ret', 'rvol', 'vwap_dist',
    'body_to_atr_x_high_vol', 'range_to_atr_x_directional',
    'side_numeric', 'window_OPEN', 'window_CLOSE'
]


def _prepare_dataset():
    df = pd.read_parquet(DATASET_PATH)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    df['side_numeric'] = (df['side'] == 'BUY').astype(int)
    df['window_OPEN'] = (df['window'] == 'OPEN').astype(int)
    df['window_CLOSE'] = (df['window'] == 'CLOSE').astype(int)
    return df


def _prepare_trades():
    trades = pd.read_csv(TRADES_PATH)
    trades['entry_dt'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    return trades


def _train_calibrated_model(df_train):
    X = df_train[FEATURE_COLS].copy()
    y = df_train['y'].copy()
    valid = ~(X.isna().any(axis=1) | y.isna())
    X = X[valid]
    y = y[valid]

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
    ])

    # Time-decay weights
    max_train_date = df_train.loc[valid, 'date'].max()
    age_days = (max_train_date - df_train.loc[valid, 'date']).dt.days
    sample_weights = np.exp(-0.001 * age_days)

    pipeline.fit(X, y, model__sample_weight=sample_weights)

    # Calibration
    n_cal = int(len(X) * 0.5)
    if n_cal < 50 or len(X) - n_cal < 50:
        return pipeline, False

    X_cal = X[:n_cal]
    y_cal = y[:n_cal]
    X_val = X[n_cal:]
    y_val = y[n_cal:]

    calibrator = CalibratedClassifierCV(estimator=pipeline, method='isotonic', cv='prefit')
    calibrator.fit(X_val, y_val)
    return calibrator, True


def _compute_trade_metrics(df_test, trades):
    # Build entry timestamp for join
    df_test = df_test.copy()
    df_test['entry_dt'] = pd.to_datetime(df_test['date'].dt.strftime('%Y-%m-%d') + ' ' + df_test['start_time'])

    trades_sub = trades[['ticker', 'entry_dt', 'r_mult']]
    merged = pd.merge(df_test, trades_sub, on=['ticker', 'entry_dt'], how='inner')

    if len(merged) == 0:
        return None

    r_vals = merged['r_mult'].values
    wins = r_vals[r_vals > 0]
    losses = r_vals[r_vals <= 0]

    wr = len(wins) / len(r_vals) if len(r_vals) else 0
    gross_profit = wins.sum() if len(wins) else 0
    gross_loss = abs(losses.sum()) if len(losses) else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else 0

    # Equity curve / max DD
    equity = 1.0
    peak = equity
    max_dd = 0.0
    for r in r_vals:
        equity *= (1 + r * 0.01)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        'trades': int(len(r_vals)),
        'wr': float(wr),
        'pf': float(pf),
        'mean_r': float(np.mean(r_vals)),
        'max_dd': float(max_dd)
    }


def _compute_auc(model, df_test):
    X = df_test[FEATURE_COLS].copy()
    y = df_test['y'].copy()
    valid = ~(X.isna().any(axis=1) | y.isna())
    X = X[valid]
    y = y[valid]

    if len(y.unique()) < 2:
        return None

    probs = model.predict_proba(X)[:, 1]
    return float(roc_auc_score(y, probs))


def extended_period_test():
    print("[RS-01] === EXTENDED HISTORICAL 2015–2020 ===\n")

    df = _prepare_dataset()
    trades = _prepare_trades()

    test_start = pd.Timestamp('2015-01-01')
    test_end = pd.Timestamp('2020-12-31')

    df_test = df[(df['date'] >= test_start) & (df['date'] <= test_end)].copy()

    results = {
        'test_window': {'start': str(test_start.date()), 'end': str(test_end.date())},
        'frozen_model': None,
        'refit_model': None
    }

    if len(df_test) == 0:
        results['error'] = 'No data in 2015–2020 window. Check dataset coverage.'
        with open(OUTPUT_DIR / 'extended_period_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("[RS-01] ⚠️ No data in 2015–2020. Results saved with error.")
        return results

    # Scenario A: Frozen model (train 2020–2025)
    train_a = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2025-06-30')].copy()
    if len(train_a) > 0:
        model_a, calibrated_a = _train_calibrated_model(train_a)
        auc_a = _compute_auc(model_a, df_test)
        metrics_a = _compute_trade_metrics(df_test, trades)
        results['frozen_model'] = {
            'train_window': {'start': '2020-01-01', 'end': '2025-06-30'},
            'calibrated': calibrated_a,
            'auc': auc_a,
            'metrics': metrics_a
        }

    # Scenario B: Refit model (train 2013–2015)
    train_b = df[(df['date'] >= '2013-01-01') & (df['date'] < '2015-01-01')].copy()
    if len(train_b) > 0:
        model_b, calibrated_b = _train_calibrated_model(train_b)
        auc_b = _compute_auc(model_b, df_test)
        metrics_b = _compute_trade_metrics(df_test, trades)
        results['refit_model'] = {
            'train_window': {'start': '2013-01-01', 'end': '2014-12-31'},
            'calibrated': calibrated_b,
            'auc': auc_b,
            'metrics': metrics_b
        }

    with open(OUTPUT_DIR / 'extended_period_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("[RS-01] Results saved to extended_period_results.json")
    return results


if __name__ == '__main__':
    extended_period_test()
