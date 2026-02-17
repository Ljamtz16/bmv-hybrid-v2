# Edge Decomposition Step 2: R Distribution Analysis
# Analyze shape, skewness, kurtosis, tail risk

import pandas as pd
import numpy as np
import json
from pathlib import Path
from scipy import stats

def analyze_r_distribution():
    """
    Analyze R distribution for edge characteristics.
    """
    print("[EDGE-02] === R DISTRIBUTION ANALYSIS ===\n")
    
    # Load OOS trades
    trades_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
    trades = pd.read_csv(trades_path)
    trades['entry_time'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    
    oos_start = pd.Timestamp('2025-07-01')
    oos_end = pd.Timestamp('2026-02-13')
    
    trades_oos = trades[(trades['entry_time'] >= oos_start) & (trades['entry_time'] <= oos_end)].copy()
    
    # Use r_mult directly
    trades_oos['r_multiple'] = trades_oos['r_mult']
    
    # Use all OOS trades
    valid_trades = trades_oos.copy()
    r_multiples = valid_trades['r_multiple'].values
    
    # Split wins and losses
    wins = r_multiples[r_multiples > 0]
    losses = r_multiples[r_multiples <= 0]
    
    print(f"[EDGE-02] Total trades: {len(r_multiples)}")
    print(f"[EDGE-02] Wins: {len(wins)}, Losses: {len(losses)}\n")
    
    # Distribution stats
    print(f"[EDGE-02] === OVERALL DISTRIBUTION ===")
    print(f"[EDGE-02] Mean: {r_multiples.mean():.4f}R")
    print(f"[EDGE-02] Median: {np.median(r_multiples):.4f}R")
    print(f"[EDGE-02] Std: {r_multiples.std():.4f}R")
    print(f"[EDGE-02] Min: {r_multiples.min():.4f}R")
    print(f"[EDGE-02] Max: {r_multiples.max():.4f}R")
    print(f"[EDGE-02] Skewness: {stats.skew(r_multiples):.4f}")
    print(f"[EDGE-02] Kurtosis: {stats.kurtosis(r_multiples):.4f}\n")
    
    # Win distribution
    print(f"[EDGE-02] === WIN DISTRIBUTION ===")
    print(f"[EDGE-02] Mean: {wins.mean():.4f}R")
    print(f"[EDGE-02] Median: {np.median(wins):.4f}R")
    print(f"[EDGE-02] Std: {wins.std():.4f}R")
    print(f"[EDGE-02] Min: {wins.min():.4f}R")
    print(f"[EDGE-02] Max: {wins.max():.4f}R\n")
    
    # Loss distribution
    print(f"[EDGE-02] === LOSS DISTRIBUTION ===")
    print(f"[EDGE-02] Mean: {losses.mean():.4f}R")
    print(f"[EDGE-02] Median: {np.median(losses):.4f}R")
    print(f"[EDGE-02] Std: {losses.std():.4f}R")
    print(f"[EDGE-02] Min: {losses.min():.4f}R")
    print(f"[EDGE-02] Max: {losses.max():.4f}R\n")
    
    # Tail analysis
    print(f"[EDGE-02] === TAIL RISK ANALYSIS ===")
    pct_loss_below_neg08 = (r_multiples < -0.8).sum() / len(r_multiples) * 100
    pct_win_above_10 = (r_multiples > 1.0).sum() / len(r_multiples) * 100
    
    print(f"[EDGE-02] % trades with R < -0.8: {pct_loss_below_neg08:.2f}%")
    print(f"[EDGE-02] % trades with R > 1.0: {pct_win_above_10:.2f}%")
    print(f"[EDGE-02] % trades with R < -1.0: {(r_multiples < -1.0).sum() / len(r_multiples) * 100:.2f}%")
    print(f"[EDGE-02] % trades with R > 1.333: {(r_multiples > 1.333).sum() / len(r_multiples) * 100:.2f}%\n")
    
    # Generate histogram data
    bins = [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.333, 2.0]
    hist, bin_edges = np.histogram(r_multiples, bins=bins)
    
    print(f"[EDGE-02] === HISTOGRAM ===")
    for i in range(len(hist)):
        print(f"[EDGE-02] {bin_edges[i]:.3f} to {bin_edges[i+1]:.3f}: {hist[i]} trades ({hist[i]/len(r_multiples)*100:.1f}%)")
    
    # Save results
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\edge_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        'mean': float(r_multiples.mean()),
        'median': float(np.median(r_multiples)),
        'std': float(r_multiples.std()),
        'min': float(r_multiples.min()),
        'max': float(r_multiples.max()),
        'skewness': float(stats.skew(r_multiples)),
        'kurtosis': float(stats.kurtosis(r_multiples)),
        'win_mean': float(wins.mean()),
        'loss_mean': float(losses.mean()),
        'pct_loss_below_08': float(pct_loss_below_neg08),
        'pct_win_above_10': float(pct_win_above_10),
        'total_trades': len(r_multiples),
        'wins': int(len(wins)),
        'losses': int(len(losses))
    }
    
    with open(output_dir / 'r_distribution_stats.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save histogram as CSV
    histogram_df = pd.DataFrame({
        'bin_start': bin_edges[:-1],
        'bin_end': bin_edges[1:],
        'count': hist,
        'pct': hist / len(r_multiples) * 100
    })
    histogram_df.to_csv(output_dir / 'r_histogram.csv', index=False)
    
    print(f"\n[EDGE-02] OK Results saved\n")
    
    return results

if __name__ == '__main__':
    analyze_r_distribution()
