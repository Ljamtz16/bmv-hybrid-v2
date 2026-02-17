# Edge Decomposition Step 6: Classification vs Execution Edge
# Compare perfect classification edge vs actual execution edge

import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

def classification_vs_execution():
    """
    Decompose edge into classification component and execution component.
    """
    print("[EDGE-06] === CLASSIFICATION vs EXECUTION EDGE ===\n")
    
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
        print("[EDGE-06] ⚠️ No matching OOS trades after join!")
        return None
    
    merged['r_multiple'] = merged['r_mult']
    
    # Use all OOS trades
    valid_trades = merged.copy()
    
    print(f"[EDGE-06] OOS trades: {len(valid_trades)}\n")
    
    # Scenario A: PERFECT CLASSIFICATION
    # If model predicts WIN (prob > 0.5): +1R, else -1R
    print(f"[EDGE-06] === SCENARIO A: PERFECT CLASSIFICATION ===")
    print(f"[EDGE-06] Assumption: Correct classification = +1R, incorrect = -1R\n")
    
    perfect_r = np.where(valid_trades['pred'] == valid_trades['y'], 1.0, -1.0)
    
    wins_perfect = perfect_r[perfect_r > 0]
    losses_perfect = perfect_r[perfect_r <= 0]
    
    wr_perfect = len(wins_perfect) / len(perfect_r)
    pf_perfect = wins_perfect.sum() / abs(losses_perfect.sum()) if len(losses_perfect) > 0 else 0
    
    # Build equity curve
    equity_perfect = 1.0
    peak_perfect = equity_perfect
    max_dd_perfect = 0
    for r in perfect_r:
        equity_perfect *= (1 + r * 0.01)
        if equity_perfect > peak_perfect:
            peak_perfect = equity_perfect
        dd = (peak_perfect - equity_perfect) / peak_perfect if peak_perfect > 0 else 0
        max_dd_perfect = max(max_dd_perfect, dd)
    
    print(f"[EDGE-06] Classification Accuracy: {wr_perfect:.4f} ({int(wr_perfect*len(perfect_r))}/{len(perfect_r)})")
    print(f"[EDGE-06] PF (perfect execution): {pf_perfect:.4f}")
    print(f"[EDGE-06] Final Equity: {equity_perfect:.4f}x")
    print(f"[EDGE-06] Max DD: {max_dd_perfect:.2%}\n")
    
    # Scenario B: ACTUAL EXECUTION
    # Use actual R-multiples with TP/SL
    print(f"[EDGE-06] === SCENARIO B: ACTUAL EXECUTION ===")
    print(f"[EDGE-06] Assumption: Use actual TP/SL R-multiples\n")
    
    r_vals_actual = valid_trades['r_multiple'].values
    
    wins_actual = r_vals_actual[r_vals_actual > 0]
    losses_actual = r_vals_actual[r_vals_actual <= 0]
    
    wr_actual = len(wins_actual) / len(r_vals_actual)
    pf_actual = wins_actual.sum() / abs(losses_actual.sum()) if len(losses_actual) > 0 else 0
    
    # Build equity curve
    equity_actual = 1.0
    peak_actual = equity_actual
    max_dd_actual = 0
    for r in r_vals_actual:
        equity_actual *= (1 + r * 0.01)
        if equity_actual > peak_actual:
            peak_actual = equity_actual
        dd = (peak_actual - equity_actual) / peak_actual if peak_actual > 0 else 0
        max_dd_actual = max(max_dd_actual, dd)
    
    print(f"[EDGE-06] Win Rate (classifications): {wr_actual:.4f}")
    print(f"[EDGE-06] PF (actual execution): {pf_actual:.4f}")
    print(f"[EDGE-06] Final Equity: {equity_actual:.4f}x")
    print(f"[EDGE-06] Max DD: {max_dd_actual:.2%}\n")
    
    # Gap Analysis
    print(f"[EDGE-06] === EDGE DECOMPOSITION ===")
    
    pf_gap = pf_perfect - pf_actual
    pf_gap_pct = (pf_gap / pf_perfect * 100) if pf_perfect > 0 else 0
    
    equity_gap = equity_perfect - equity_actual
    equity_gap_pct = (equity_gap / equity_perfect * 100) if equity_perfect > 0 else 0
    
    print(f"[EDGE-06] Classification Edge (perfect execution): PF {pf_perfect:.4f}")
    print(f"[EDGE-06] Execution Edge (actual TP/SL): PF {pf_actual:.4f}")
    print(f"[EDGE-06] Gap: {pf_gap:.4f} ({pf_gap_pct:.2f}%)\n")
    
    # Verdict
    if pf_perfect > 2 and pf_actual > 1.5:
        verdict = "BOTH_STRONG"
        interpretation = "Classifier is strong AND execution layer preserves edge (institutional grade)"
    elif pf_perfect > 2 and pf_actual < 1.2:
        verdict = "CLASSIFIER_STRONG_EXECUTION_WEAK"
        interpretation = "Strong classification but execution layer erodes edge significantly"
    elif pf_perfect < 1.5 and pf_actual > 1.5:
        verdict = "EXECUTION_STRONG_CLASSIFIER_WEAK"
        interpretation = "Classifier weak but TP/SL execution creates edge (unusual)"
    elif pf_perfect < 1.2 and pf_actual < 1.2:
        verdict = "ILLUSION"
        interpretation = "No real edge; calibration or backtest artifact"
    else:
        verdict = "MIXED"
        interpretation = "Unclear edge structure"
    
    print(f"[EDGE-06] === VERDICT ===")
    print(f"[EDGE-06] {verdict}")
    print(f"[EDGE-06] {interpretation}\n")
    
    # Save results
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\edge_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        'verdict': verdict,
        'interpretation': interpretation,
        'classification_edge': {
            'accuracy': float(wr_perfect),
            'pf': float(pf_perfect),
            'final_equity': float(equity_perfect),
            'max_dd': float(max_dd_perfect)
        },
        'execution_edge': {
            'win_rate': float(wr_actual),
            'pf': float(pf_actual),
            'final_equity': float(equity_actual),
            'max_dd': float(max_dd_actual)
        },
        'gap_analysis': {
            'pf_gap': float(pf_gap),
            'pf_gap_pct': float(pf_gap_pct),
            'equity_gap': float(equity_gap),
            'equity_gap_pct': float(equity_gap_pct)
        }
    }
    
    with open(output_dir / 'classification_vs_execution.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"[EDGE-06] OK Results saved to classification_vs_execution.json\n")
    
    return results

if __name__ == '__main__':
    classification_vs_execution()
