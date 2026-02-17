# Edge Decomposition Step 5: Probability-Based Position Sizing
# Test if dynamic sizing (edge * 3) improves PF

import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

def probability_position_sizing():
    """
    Test probability-based position sizing and measure monetization.
    """
    print("[EDGE-05] === PROBABILITY-BASED POSITION SIZING ===\n")
    
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
    
    # Train model
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
    
    # Get OOS data
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
    
    # Load trades and join on ticker + entry time
    trades = pd.read_csv(trades_path)
    trades['entry_dt'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    trades_oos = trades[(trades['entry_dt'] >= oos_start) & (trades['entry_dt'] <= oos_end)].copy()
    trades_oos = trades_oos[['ticker', 'entry_dt', 'r_mult', 'exit_reason']]
    
    merged = pd.merge(df_oos_clean, trades_oos, on=['ticker', 'entry_dt'], how='inner')
    if len(merged) == 0:
        print("[EDGE-05] ⚠️ No matching OOS trades after join!")
        return None
    
    merged['r_multiple'] = merged['r_mult']
    
    # Use all OOS trades
    valid_trades = merged.copy()
    
    if len(valid_trades) == 0:
        print("[EDGE-05] ⚠️ No valid trades!")
        return None
    
    print(f"[EDGE-05] OOS trades: {len(valid_trades)}\n")
    
    # Scenario 1: FLAT SIZING (1R per trade)
    print(f"[EDGE-05] === SCENARIO 1: FLAT SIZING (1R) ===")
    r_vals_flat = valid_trades['r_multiple'].values
    
    wins_flat = r_vals_flat[r_vals_flat > 0]
    losses_flat = r_vals_flat[r_vals_flat <= 0]
    
    pf_flat = wins_flat.sum() / abs(losses_flat.sum()) if len(losses_flat) > 0 else 0
    wr_flat = len(wins_flat) / len(r_vals_flat)
    
    # Build equity curve (flat)
    equity_flat = 1.0
    equity_curve_flat = [equity_flat]
    peak_flat = equity_flat
    max_dd_flat = 0
    
    for r in r_vals_flat:
        equity_flat *= (1 + r * 0.01)
        equity_curve_flat.append(equity_flat)
        if equity_flat > peak_flat:
            peak_flat = equity_flat
        dd = (peak_flat - equity_flat) / peak_flat if peak_flat > 0 else 0
        max_dd_flat = max(max_dd_flat, dd)
    
    print(f"[EDGE-05] WR: {wr_flat:.4f}")
    print(f"[EDGE-05] PF: {pf_flat:.4f}")
    print(f"[EDGE-05] Final Equity: {equity_flat:.4f}x")
    print(f"[EDGE-05] Max DD: {max_dd_flat:.2%}\n")
    
    # Scenario 2: DYNAMIC SIZING (edge * 3, clipped 0.5-2.0)
    print(f"[EDGE-05] === SCENARIO 2: DYNAMIC SIZING (edge * 3) ===")
    
    valid_trades['edge'] = valid_trades['prob'] - 0.5
    valid_trades['size_mult'] = np.clip(valid_trades['edge'] * 3, 0.5, 2.0)
    valid_trades['r_adjusted'] = valid_trades['r_multiple'] * valid_trades['size_mult']
    
    r_vals_dynamic = valid_trades['r_adjusted'].values
    
    wins_dynamic = r_vals_dynamic[r_vals_dynamic > 0]
    losses_dynamic = r_vals_dynamic[r_vals_dynamic <= 0]
    
    pf_dynamic = wins_dynamic.sum() / abs(losses_dynamic.sum()) if len(losses_dynamic) > 0 else 0
    wr_dynamic = (valid_trades['r_multiple'] > 0).sum() / len(valid_trades)
    
    # Build equity curve (dynamic)
    equity_dynamic = 1.0
    equity_curve_dynamic = [equity_dynamic]
    peak_dynamic = equity_dynamic
    max_dd_dynamic = 0
    
    for r in r_vals_dynamic:
        equity_dynamic *= (1 + r * 0.01)
        equity_curve_dynamic.append(equity_dynamic)
        if equity_dynamic > peak_dynamic:
            peak_dynamic = equity_dynamic
        dd = (peak_dynamic - equity_dynamic) / peak_dynamic if peak_dynamic > 0 else 0
        max_dd_dynamic = max(max_dd_dynamic, dd)
    
    print(f"[EDGE-05] WR: {wr_dynamic:.4f} (same as flat)")
    print(f"[EDGE-05] PF: {pf_dynamic:.4f}")
    print(f"[EDGE-05] Final Equity: {equity_dynamic:.4f}x")
    print(f"[EDGE-05] Max DD: {max_dd_dynamic:.2%}\n")
    
    # Comparison
    print(f"[EDGE-05] === COMPARISON ===")
    pf_improvement = (pf_dynamic - pf_flat) / pf_flat * 100 if pf_flat > 0 else 0
    equity_improvement = (equity_dynamic - equity_flat) / equity_flat * 100
    
    print(f"[EDGE-05] PF improvement: {pf_improvement:+.2f}%")
    print(f"[EDGE-05] Equity improvement: {equity_improvement:+.2f}%")
    print(f"[EDGE-05] Max DD change: {(max_dd_dynamic - max_dd_flat)*100:+.2f}%\n")
    
    if pf_improvement > 10:
        print(f"[EDGE-05] ✅ DYNAMIC SIZING IMPROVES PF MATERIALLY\n")
        sizing_verdict = "DYNAMIC_IMPROVES"
    else:
        print(f"[EDGE-05] ⚠️ DYNAMIC SIZING MINIMAL IMPACT\n")
        sizing_verdict = "NO_MATERIAL_IMPACT"
    
    # Save results
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\edge_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        'sizing_verdict': sizing_verdict,
        'flat_sizing': {
            'wr': float(wr_flat),
            'pf': float(pf_flat),
            'final_equity': float(equity_flat),
            'max_dd': float(max_dd_flat)
        },
        'dynamic_sizing': {
            'wr': float(wr_dynamic),
            'pf': float(pf_dynamic),
            'final_equity': float(equity_dynamic),
            'max_dd': float(max_dd_dynamic)
        },
        'improvement': {
            'pf_pct': float(pf_improvement),
            'equity_pct': float(equity_improvement),
            'dd_change_pct': float((max_dd_dynamic - max_dd_flat)*100)
        }
    }
    
    with open(output_dir / 'probability_sizing_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"[EDGE-05] OK Results saved to probability_sizing_results.json\n")
    
    return results

if __name__ == '__main__':
    probability_position_sizing()
