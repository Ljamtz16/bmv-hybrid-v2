# Audit Test 5: Monte Carlo Equity Simulation
# Use actual R-multiples from backtest trades
# Simulate 10,000 random reorderings to assess risk
#
# Output: artifacts/audit/monte_carlo_summary.json
#         artifacts/audit/monte_carlo_equity_curves.csv

import pandas as pd
import numpy as np
import json
from pathlib import Path


def monte_carlo_equity_simulation(n_simulations=10000):
    """
    Monte Carlo: resample trade sequence to assess equity curve stability and ruin risk
    """
    print("[AUDIT-05] === MONTE CARLO EQUITY SIMULATION ===\n")
    
    # === Load trades ===
    trades_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
    print(f"[AUDIT-05] Loading trades from {trades_path}...")
    trades = pd.read_csv(trades_path)
    
    # Calculate R-multiples
    # R-multiple = (exit_price - entry_price) / (entry_price - sl_price)
    trades['r_multiple'] = (trades['exit_price'] - trades['entry_price']) / (trades['entry_price'] - trades['sl_price'])
    
    # Filter valid trades (TP/SL only, exclude TIMEOUT/DAILY_STOP)
    valid_trades = trades[trades['exit_reason'].isin(['TP', 'SL'])].copy()
    
    print(f"[AUDIT-05] Total trades: {len(trades)}")
    print(f"[AUDIT-05] Valid trades (TP/SL): {len(valid_trades)}")
    print(f"[AUDIT-05] Mean R-multiple: {valid_trades['r_multiple'].mean():.3f}")
    print(f"[AUDIT-05] Std R-multiple: {valid_trades['r_multiple'].std():.3f}")
    print(f"[AUDIT-05] Min R-multiple: {valid_trades['r_multiple'].min():.3f}")
    print(f"[AUDIT-05] Max R-multiple: {valid_trades['r_multiple'].max():.3f}\n")
    
    if len(valid_trades) == 0:
        print("[AUDIT-05] ⚠️ No valid trades found!")
        return None
    
    # === Monte Carlo simulations ===
    print(f"[AUDIT-05] Running {n_simulations:,} Monte Carlo simulations...\n")
    
    r_multiples = valid_trades['r_multiple'].values
    base_r = 0.01  # 1R per trade
    
    mc_results = []
    final_equities = []
    max_dds = []
    
    for sim in range(n_simulations):
        # Resample trades with replacement
        sampled_rs = np.random.choice(r_multiples, size=len(valid_trades), replace=True)
        
        # Build equity curve
        equity = 1.0
        equity_curve = [equity]
        peak = equity
        
        for r in sampled_rs:
            pnl_pct = r * base_r
            equity *= (1 + pnl_pct)
            equity_curve.append(equity)
            
            if equity > peak:
                peak = equity
            
            # Check for ruin (equity drops to 0)
            if equity <= 0:
                equity = 0
                break
        
        final_equity = equity_curve[-1]
        max_dd = ((min(equity_curve) - peak) / peak * 100) if peak > 0 else 0
        
        final_equities.append(final_equity)
        max_dds.append(max_dd)
        mc_results.append(equity_curve)
        
        if (sim + 1) % (n_simulations // 10) == 0:
            print(f"[AUDIT-05]   {sim+1:,}/{n_simulations:,} simulations complete")
    
    # === Analysis ===
    final_equities = np.array(final_equities)
    max_dds = np.array(max_dds)
    
    prob_ruin = (final_equities <= 0).sum() / len(final_equities) * 100
    percentile_5 = np.percentile(final_equities[final_equities > 0], 5) if (final_equities > 0).any() else 0
    percentile_95 = np.percentile(final_equities[final_equities > 0], 95) if (final_equities > 0).any() else 0
    mean_final = final_equities[final_equities > 0].mean() if (final_equities > 0).any() else 0
    median_final = np.median(final_equities[final_equities > 0]) if (final_equities > 0).any() else 0
    
    mean_max_dd = max_dds[final_equities > 0].mean() if (final_equities > 0).any() else 0
    
    print(f"\n[AUDIT-05] === MONTE CARLO RESULTS ===")
    print(f"[AUDIT-05] Simulations completed: {n_simulations:,}")
    print(f"[AUDIT-05] Probability of ruin (equity ≤ 0): {prob_ruin:.2f}%")
    print(f"[AUDIT-05] Final equity distribution (non-ruined):")
    print(f"[AUDIT-05]   5th percentile: {percentile_5:.3f}")
    print(f"[AUDIT-05]   Mean: {mean_final:.3f}")
    print(f"[AUDIT-05]   Median: {median_final:.3f}")
    print(f"[AUDIT-05]   95th percentile: {percentile_95:.3f}")
    print(f"[AUDIT-05] Average max drawdown: {mean_max_dd:.1f}%")
    
    # Verdict
    if prob_ruin > 5:
        print(f"\n[AUDIT-05] ⚠️ WARNING: High ruin probability (>{prob_ruin:.1f}%)")
        verdict = 'YELLOW'
    elif mean_final < 1.05:
        print(f"\n[AUDIT-05] ⚠️ WARNING: Poor expected growth (mean={mean_final:.3f})")
        verdict = 'YELLOW'
    else:
        print(f"\n[AUDIT-05] ✅ PASS: Robust equity growth, low ruin risk")
        verdict = 'GREEN'
    
    print(f"[AUDIT-05] Verdict: {verdict}")
    
    # === Save results ===
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Summary
    summary = {
        'simulations': n_simulations,
        'trades_sampled': len(valid_trades),
        'probability_of_ruin_pct': float(prob_ruin),
        'final_equity_distribution': {
            'percentile_5': float(percentile_5),
            'mean': float(mean_final),
            'median': float(median_final),
            'percentile_95': float(percentile_95)
        },
        'drawdown': {
            'mean_max_dd_pct': float(mean_max_dd)
        },
        'verdict': verdict
    }
    
    with open(output_dir / 'monte_carlo_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Save sample equity curves (first 100 simulations)
    df_mc_curves = []
    for sim_id, curve in enumerate(mc_results[:100]):
        for step, equity in enumerate(curve):
            df_mc_curves.append({
                'simulation': sim_id,
                'step': step,
                'equity': equity
            })
    
    df_mc_df = pd.DataFrame(df_mc_curves)
    df_mc_df.to_csv(output_dir / 'monte_carlo_equity_curves.csv', index=False)
    
    print(f"\n[AUDIT-05] ✅ Results saved")
    print(f"[AUDIT-05]   - monte_carlo_summary.json")
    print(f"[AUDIT-05]   - monte_carlo_equity_curves.csv (100 sample curves)")
    
    return summary


if __name__ == '__main__':
    results = monte_carlo_equity_simulation(n_simulations=10000)
