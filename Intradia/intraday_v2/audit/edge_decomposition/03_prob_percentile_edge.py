# Edge Decomposition Step 3: Probability Percentile Edge Analysis
# Verify monotonicity: higher prob -> higher WR & expectancy

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

def prob_percentile_edge():
    """
    Group OOS trades by probability percentiles and compute edge metrics.
    """
    print("[EDGE-03] === PROBABILITY PERCENTILE EDGE ANALYSIS ===\n")
    
    # Load dataset
    dataset_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    trades_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
    df = pd.read_parquet(dataset_path)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    
    # Add categorical features
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
    
    # Train on full dataset (for initial model)
    X = df[feature_cols].copy()
    y = df['y'].copy()
    
    # Remove NaN
    valid = ~(X.isna().any(axis=1) | y.isna())
    X = X[valid]
    y = y[valid]
    
    # Train model
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
    ])
    pipeline.fit(X, y)
    
    # Get OOS probabilities
    oos_start = pd.Timestamp('2025-07-01')
    oos_end = pd.Timestamp('2026-02-13')
    
    df_oos = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)].copy()
    
    if len(df_oos) == 0:
        print("[EDGE-03] ⚠️ No OOS data found!")
        return None
    
    X_oos = df_oos[feature_cols].copy()
    y_oos = df_oos['y'].copy()
    
    # Remove NaN
    oos_valid = ~(X_oos.isna().any(axis=1) | y_oos.isna())
    X_oos = X_oos[oos_valid]
    y_oos = y_oos[oos_valid]
    df_oos_clean = df_oos[oos_valid].copy()
    
    print(f"[EDGE-03] OOS samples: {len(X_oos)}\n")
    
    # Get probabilities
    probs = pipeline.predict_proba(X_oos)[:, 1]
    df_oos_clean['prob'] = probs
    df_oos_clean['pred'] = (probs > 0.5).astype(int)
    
    # Build entry timestamp for join
    df_oos_clean['entry_dt'] = pd.to_datetime(df_oos_clean['date'].dt.strftime('%Y-%m-%d') + ' ' + df_oos_clean['start_time'])
    
    # Load trades and join on ticker + entry time
    trades = pd.read_csv(trades_path)
    trades['entry_dt'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    trades_oos = trades[(trades['entry_dt'] >= oos_start) & (trades['entry_dt'] <= oos_end)].copy()
    trades_oos = trades_oos[['ticker', 'entry_dt', 'r_mult', 'exit_reason']]
    
    merged = pd.merge(df_oos_clean, trades_oos, on=['ticker', 'entry_dt'], how='inner')
    if len(merged) == 0:
        print("[EDGE-03] ⚠️ No matching OOS trades after join!")
        return None
    
    merged['r_multiple'] = merged['r_mult']
    
    # Define percentile buckets
    buckets = [
        (0.70, 0.75, '70-75%'),
        (0.75, 0.80, '75-80%'),
        (0.80, 0.85, '80-85%'),
        (0.85, 0.90, '85-90%'),
        (0.90, 0.95, '90-95%'),
        (0.95, 1.00, '95-100%')
    ]
    
    results = []
    print(f"[EDGE-03] === PROBABILITY PERCENTILE ANALYSIS ===\n")
    
    for min_prob, max_prob, label in buckets:
        bucket_data = merged[(merged['prob'] >= min_prob) & (merged['prob'] < max_prob)]
        
        if len(bucket_data) == 0:
            continue
        
        r_vals = bucket_data['r_multiple'].values
        wins = r_vals[r_vals > 0]
        losses = r_vals[r_vals <= 0]
        
        wr = len(wins) / len(r_vals) if len(r_vals) > 0 else 0
        
        if len(losses) > 0:
            gross_profit = wins.sum() if len(wins) > 0 else 0
            gross_loss = abs(losses.sum())
            pf = gross_profit / gross_loss if gross_loss > 0 else 0
        else:
            pf = 0
        
        avg_r = r_vals.mean()
        expectancy = avg_r
        
        print(f"[EDGE-03] Prob {label}:")
        print(f"[EDGE-03]   Trades: {len(r_vals)}")
        print(f"[EDGE-03]   WR: {wr:.4f} ({len(wins)}/{len(r_vals)})")
        print(f"[EDGE-03]   PF: {pf:.4f}")
        print(f"[EDGE-03]   Avg R: {avg_r:.4f}R")
        print(f"[EDGE-03]   Expectancy: {expectancy:.4f}R\n")
        
        results.append({
            'prob_range': label,
            'min_prob': min_prob,
            'max_prob': max_prob,
            'trades': len(r_vals),
            'wins': int(len(wins)),
            'losses': int(len(losses)),
            'wr': float(wr),
            'pf': float(pf),
            'avg_r': float(avg_r),
            'expectancy': float(expectancy)
        })
    
    # Check monotonicity
    print(f"[EDGE-03] === MONOTONICITY CHECK ===")
    wr_values = [r['wr'] for r in results]
    expectancy_values = [r['expectancy'] for r in results]
    
    is_monotonic_wr = all(wr_values[i] <= wr_values[i+1] for i in range(len(wr_values)-1))
    is_monotonic_exp = all(expectancy_values[i] <= expectancy_values[i+1] for i in range(len(expectancy_values)-1))
    
    if is_monotonic_wr and is_monotonic_exp:
        print(f"[EDGE-03] ✅ PASS: Monotonic relationship (prob -> WR -> expectancy)\n")
        status = "MONOTONIC"
    else:
        print(f"[EDGE-03] ⚠️ WARNING: Non-monotonic relationship (calibration illusion?)\n")
        status = "NON_MONOTONIC"
    
    # Save results
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\edge_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_dir / 'prob_percentile_edge.csv', index=False)
    
    print(f"[EDGE-03] OK Results saved to prob_percentile_edge.csv\n")
    
    return results

if __name__ == '__main__':
    prob_percentile_edge()
