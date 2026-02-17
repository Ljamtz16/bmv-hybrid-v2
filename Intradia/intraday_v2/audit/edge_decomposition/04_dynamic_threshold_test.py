# Edge Decomposition Step 4: Dynamic Threshold Test
# Test different thresholds (top 50%, 30%, 20%, 10% per month)

import pandas as pd
import numpy as np
from pathlib import Path
from dateutil.relativedelta import relativedelta

def dynamic_threshold_test():
    """
    Test different probability thresholds and measure edge concentration.
    """
    print("[EDGE-04] === DYNAMIC THRESHOLD TEST ===\n")
    
    # Load OOS trades
    trades_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
    dataset_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'
    
    trades = pd.read_csv(trades_path)
    trades['entry_dt'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
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
    
    # Train model (full data)
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    
    X = df[feature_cols].copy()
    y = df['y'].copy()
    valid = ~(X.isna().any(axis=1) | y.isna())
    X = X[valid]
    y = y[valid]
    
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42, solver='lbfgs'))
    ])
    pipeline.fit(X, y)
    
    # Get OOS probabilities
    oos_start = pd.Timestamp('2025-07-01')
    oos_end = pd.Timestamp('2026-02-13')
    
    df_oos = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)].copy()
    X_oos = df_oos[feature_cols].copy()
    oos_valid = ~(X_oos.isna().any(axis=1) | df_oos['y'].isna())
    X_oos = X_oos[oos_valid]
    df_oos_clean = df_oos[oos_valid].copy()
    
    probs = pipeline.predict_proba(X_oos)[:, 1]
    df_oos_clean['prob'] = probs
    
    # Build entry timestamp for join
    df_oos_clean['entry_dt'] = pd.to_datetime(df_oos_clean['date'].dt.strftime('%Y-%m-%d') + ' ' + df_oos_clean['start_time'])
    
    trades_oos = trades[(trades['entry_dt'] >= oos_start) & (trades['entry_dt'] <= oos_end)].copy()
    trades_oos = trades_oos[['ticker', 'entry_dt', 'r_mult', 'exit_reason']]
    
    merged = pd.merge(df_oos_clean, trades_oos, on=['ticker', 'entry_dt'], how='inner')
    if len(merged) == 0:
        print("[EDGE-04] ⚠️ No matching OOS trades after join!")
        return None
    
    merged['r_multiple'] = merged['r_mult']
    
    results = []
    
    thresholds = [
        ('Top 50%', 0.50),
        ('Top 30%', 0.70),
        ('Top 20%', 0.80),
        ('Top 10%', 0.90)
    ]
    
    print(f"[EDGE-04] === THRESHOLD ANALYSIS ===\n")
    
    for label, threshold in thresholds:
        # Filter by threshold
        filtered = merged[merged['prob'] >= threshold].copy()
        
        if len(filtered) == 0:
            continue
        
        if len(filtered) == 0:
            continue
        
        r_vals = filtered['r_multiple'].values
        wins = r_vals[r_vals > 0]
        losses = r_vals[r_vals <= 0]
        
        wr = len(wins) / len(r_vals)
        gross_profit = wins.sum() if len(wins) > 0 else 0
        gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Max DD
        equity = 1.0
        peak = equity
        max_dd = 0
        for r in r_vals:
            equity *= (1 + r * 0.01)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        print(f"[EDGE-04] {label}:")
        print(f"[EDGE-04]   Trades: {len(r_vals)}")
        print(f"[EDGE-04]   WR: {wr:.4f}")
        print(f"[EDGE-04]   PF: {pf:.4f}")
        print(f"[EDGE-04]   Avg R: {r_vals.mean():.4f}R")
        print(f"[EDGE-04]   Max DD: {max_dd:.2%}\n")
        
        results.append({
            'threshold_label': label,
            'threshold_prob': threshold,
            'trades': len(r_vals),
            'wr': float(wr),
            'pf': float(pf),
            'avg_r': float(r_vals.mean()),
            'max_dd': float(max_dd)
        })
    
    # Analysis
    print(f"[EDGE-04] === CONCENTRATION ANALYSIS ===")
    if len(results) >= 2:
        pf_full = results[0]['pf']
        pf_top10 = results[-1]['pf']
        concentration = pf_top10 / pf_full if pf_full > 0 else 0
        print(f"[EDGE-04] PF Full sample: {pf_full:.4f}")
        print(f"[EDGE-04] PF Top 10%: {pf_top10:.4f}")
        print(f"[EDGE-04] Concentration ratio: {concentration:.2f}x\n")
        
        if concentration > 1.5:
            print(f"[EDGE-04] ⚠️ Edge concentrates in top decile (ranking strong, execution weak)\n")
        else:
            print(f"[EDGE-04] ✅ Edge distributed across probabilities\n")
    
    # Save results
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\edge_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_dir / 'dynamic_threshold_results.csv', index=False)
    
    print(f"[EDGE-04] OK Results saved to dynamic_threshold_results.csv\n")
    
    return results

if __name__ == '__main__':
    dynamic_threshold_test()
