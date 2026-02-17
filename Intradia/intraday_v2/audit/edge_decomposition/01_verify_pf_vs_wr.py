# Edge Decomposition Step 1: Verify PF vs WR Consistency
# Load OOS trades and verify theoretical vs actual PF

import pandas as pd
import numpy as np
import json
from pathlib import Path

def verify_pf_vs_wr():
    """
    Verify that PF = (WR * avg_win) / ((1-WR) * avg_loss)
    """
    print("[EDGE-01] === PF vs WR CONSISTENCY CHECK ===\n")
    
    # Load OOS trades (2025-07-01 to 2026-02-13)
    trades_path = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
    trades = pd.read_csv(trades_path)
    trades['entry_time'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
    
    oos_start = pd.Timestamp('2025-07-01')
    oos_end = pd.Timestamp('2026-02-13')
    
    trades_oos = trades[(trades['entry_time'] >= oos_start) & (trades['entry_time'] <= oos_end)].copy()
    
    print(f"[EDGE-01] OOS Period: {oos_start.date()} to {oos_end.date()}")
    print(f"[EDGE-01] Total OOS trades: {len(trades_oos)}\n")
    
    # Use r_mult directly (already calculated)
    trades_oos['r_multiple'] = trades_oos['r_mult']
    
    # Use all OOS trades
    valid_trades = trades_oos.copy()
    
    print(f"[EDGE-01] Trades used: {len(valid_trades)}")
    
    if len(valid_trades) == 0:
        print("[EDGE-01] ⚠️ No OOS trades!")
        return None
    
    r_multiples = valid_trades['r_multiple'].values
    
    # Compute basic metrics
    wins = r_multiples[r_multiples > 0]
    losses = r_multiples[r_multiples <= 0]
    
    print(f"[EDGE-01] Wins: {len(wins)}, Losses: {len(losses)}\n")
    
    # Actual metrics
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    pf_actual = gross_profit / gross_loss if gross_loss != 0 else 0
    wr_actual = len(wins) / len(r_multiples)
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss_abs = abs(losses.mean()) if len(losses) > 0 else 0
    
    print(f"[EDGE-01] === ACTUAL METRICS ===")
    print(f"[EDGE-01] Win Rate: {wr_actual:.4f} ({len(wins)}/{len(r_multiples)})")
    print(f"[EDGE-01] Avg Win: {avg_win:.4f}R")
    print(f"[EDGE-01] Avg Loss: {avg_loss_abs:.4f}R")
    print(f"[EDGE-01] Gross Profit: {gross_profit:.4f}R")
    print(f"[EDGE-01] Gross Loss: {gross_loss:.4f}R")
    print(f"[EDGE-01] PF (Actual): {pf_actual:.4f}\n")
    
    # Theoretical PF
    if (1 - wr_actual) > 0 and avg_loss_abs > 0:
        pf_theoretical = (wr_actual * avg_win) / ((1 - wr_actual) * avg_loss_abs)
    else:
        pf_theoretical = 0
    
    print(f"[EDGE-01] === THEORETICAL PF ===")
    print(f"[EDGE-01] Formula: (WR * avg_win) / ((1-WR) * avg_loss)")
    print(f"[EDGE-01] PF (Theoretical): {pf_theoretical:.4f}\n")
    
    # Consistency check
    if pf_actual > 0:
        pf_diff_pct = abs(pf_actual - pf_theoretical) / pf_actual * 100
    else:
        pf_diff_pct = 0
    
    print(f"[EDGE-01] === CONSISTENCY CHECK ===")
    print(f"[EDGE-01] Difference: {pf_diff_pct:.2f}%")
    
    if pf_diff_pct > 5:
        print(f"[EDGE-01] ⚠️ WARNING: PF mismatch > 5% (execution or accounting issue)")
        status = "MISMATCH"
    else:
        print(f"[EDGE-01] ✅ PASS: PF consistent (difference < 5%)")
        status = "CONSISTENT"
    
    # Additional stats
    print(f"\n[EDGE-01] === ADDITIONAL STATS ===")
    print(f"[EDGE-01] Total R: {r_multiples.sum():.4f}R")
    print(f"[EDGE-01] Mean R: {r_multiples.mean():.4f}R")
    print(f"[EDGE-01] Std R: {r_multiples.std():.4f}R")
    print(f"[EDGE-01] Min R: {r_multiples.min():.4f}R")
    print(f"[EDGE-01] Max R: {r_multiples.max():.4f}R")
    
    # Save results
    output_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\audit\edge_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        'status': status,
        'pf_actual': float(pf_actual),
        'pf_theoretical': float(pf_theoretical),
        'pf_diff_pct': float(pf_diff_pct),
        'wr': float(wr_actual),
        'avg_win': float(avg_win),
        'avg_loss_abs': float(avg_loss_abs),
        'gross_profit': float(gross_profit),
        'gross_loss': float(gross_loss),
        'total_trades': len(valid_trades),
        'wins': int(len(wins)),
        'losses': int(len(losses)),
        'mean_r': float(r_multiples.mean()),
        'std_r': float(r_multiples.std()),
        'total_r': float(r_multiples.sum())
    }
    
    with open(output_dir / 'pf_consistency_check.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n[EDGE-01] OK Results saved to pf_consistency_check.json\n")
    
    return results

if __name__ == '__main__':
    verify_pf_vs_wr()
