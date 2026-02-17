"""
Test multiple prob_win thresholds - Sequential execution
Runs complete weekly backtests for different thresholds
"""

import subprocess
import pandas as pd
import json
from pathlib import Path
import time
from datetime import datetime

# ==============================================================================
# CONFIGURATION
# ==============================================================================
THRESHOLDS = [0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70]

print("=" * 100)
print("TESTING MULTIPLE PROB_WIN THRESHOLDS - 2024-2025 WEEKLY BACKTEST")
print("=" * 100)
print(f"\nConfiguration:")
print(f"  Thresholds: {THRESHOLDS}")
print(f"  Period: 2024-2025 (105 weeks)")
print(f"  Capital: $2000, Max Deploy: $1900, Max Open: 4, Per Trade: $500")
print(f"  Total executions: {len(THRESHOLDS)} x 105 weeks = {len(THRESHOLDS) * 105} backtests")
print(f"\nEstimated time: ~{len(THRESHOLDS) * 15} minutes")
print("\n" + "=" * 100)

results_comparison = []
start_time_total = time.time()

for idx, threshold in enumerate(THRESHOLDS, 1):
    print(f"\n{'='*100}")
    print(f"[{idx}/{len(THRESHOLDS)}] TESTING PROB_WIN >= {threshold:.2f}")
    print(f"{'='*100}")
    
    output_dir = f"evidence/probwin_tests/pw_{int(threshold*100)}"
    
    # Run weekly backtest with this threshold
    start_time = time.time()
    
    cmd = [
        './.venv/Scripts/python.exe',
        'backtest_weekly.py',
        '--pw_threshold', str(threshold),
        '--output_base', output_dir
    ]
    
    print(f"\nRunning: {' '.join(cmd)}")
    print(f"Output: {output_dir}/")
    print(f"\nExecuting 105 weekly backtests...")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
            encoding='utf-8'
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            # Load summary
            summary_file = Path(f'{output_dir}/weekly_summary.json')
            
            if summary_file.exists():
                with open(summary_file) as f:
                    summary = json.load(f)
                
                results_comparison.append({
                    'threshold': threshold,
                    'total_weeks': summary.get('total_weeks', 0),
                    'positive_weeks': summary.get('positive_weeks', 0),
                    'positive_pct': summary.get('positive_weeks', 0) / summary.get('total_weeks', 1) * 100,
                    'avg_return_weekly': summary.get('overall_avg_return', 0),
                    'total_pnl': summary.get('overall_total_pnl', 0),
                    'total_trades': summary.get('overall_total_trades', 0),
                    'avg_win_rate': summary.get('overall_avg_win_rate', 0) * 100,
                    'return_std': summary.get('return_std_dev', 0),
                    'sharpe_approx': summary.get('overall_avg_return', 0) / max(summary.get('return_std_dev', 1), 0.01),
                    'best_week': summary.get('best_week', {}).get('return', 0),
                    'worst_week': summary.get('worst_week', {}).get('return', 0),
                    'elapsed_sec': elapsed,
                    'status': '✅'
                })
                
                print(f"\n✅ COMPLETED in {elapsed:.0f}s ({elapsed/60:.1f} min)")
                print(f"\n   RESULTS:")
                print(f"   • Avg Return:     {summary.get('overall_avg_return', 0):+.2f}%/week")
                print(f"   • Total PnL:      ${summary.get('overall_total_pnl', 0):+,.2f}")
                print(f"   • Total Trades:   {summary.get('overall_total_trades', 0)}")
                print(f"   • Avg Win Rate:   {summary.get('overall_avg_win_rate', 0):.1%}")
                print(f"   • Positive Weeks: {summary.get('positive_weeks', 0)}/{summary.get('total_weeks', 0)}")
                print(f"   • Std Dev:        {summary.get('return_std_dev', 0):.2f}%")
            else:
                print(f"\n❌ Summary file not found: {summary_file}")
                results_comparison.append({
                    'threshold': threshold,
                    'status': '❌ No summary',
                    'elapsed_sec': elapsed
                })
        else:
            print(f"\n❌ ERROR (exit code {result.returncode})")
            print(f"STDERR: {result.stderr[:200]}")
            results_comparison.append({
                'threshold': threshold,
                'status': f'❌ Error {result.returncode}',
                'elapsed_sec': elapsed
            })
            
    except subprocess.TimeoutExpired:
        print(f"\n❌ TIMEOUT after 1 hour")
        results_comparison.append({
            'threshold': threshold,
            'status': '❌ Timeout'
        })
    except Exception as e:
        print(f"\n❌ EXCEPTION: {str(e)}")
        results_comparison.append({
            'threshold': threshold,
            'status': f'❌ {str(e)[:50]}'
        })

# ==============================================================================
# COMPARATIVE ANALYSIS
# ==============================================================================
total_elapsed = time.time() - start_time_total

print("\n" + "=" * 100)
print("COMPARATIVE ANALYSIS - ALL THRESHOLDS")
print("=" * 100)
print(f"\nTotal execution time: {total_elapsed/60:.1f} minutes")

if results_comparison:
    df = pd.DataFrame(results_comparison)
    
    # Filter successful runs
    df_success = df[df['status'] == '✅'].copy()
    
    if len(df_success) > 0:
        # Sort by avg return
        df_success = df_success.sort_values('avg_return_weekly', ascending=False)
        
        print("\n" + "=" * 100)
        print("RANKING BY AVERAGE WEEKLY RETURN")
        print("=" * 100)
        
        print(df_success[['threshold', 'avg_return_weekly', 'total_trades', 'avg_win_rate', 'positive_pct', 'sharpe_approx']].to_string(index=False))
        
        print("\n" + "=" * 100)
        print("DETAILED COMPARISON")
        print("=" * 100)
        
        for _, row in df_success.iterrows():
            print(f"\n┌─ Prob_Win >= {row['threshold']:.2f} ─────────────────")
            print(f"│ Avg Return:      {row['avg_return_weekly']:+.2f}%/week ({row['avg_return_weekly']*52:+.1f}% annualized)")
            print(f"│ Total PnL:       ${row['total_pnl']:+,.2f}")
            print(f"│ Total Trades:    {row['total_trades']}")
            print(f"│ Avg Win Rate:    {row['avg_win_rate']:.1f}%")
            print(f"│ Positive Weeks:  {row['positive_weeks']}/{row['total_weeks']} ({row['positive_pct']:.1f}%)")
            print(f"│ Std Dev:         {row['return_std']:.2f}%")
            print(f"│ Sharpe (approx): {row['sharpe_approx']:.2f}")
            print(f"│ Best Week:       {row['best_week']:+.2f}%")
            print(f"│ Worst Week:      {row['worst_week']:+.2f}%")
            print(f"│ Execution Time:  {row['elapsed_sec']/60:.1f} min")
            print(f"└{'─'*40}")
        
        # Save comparison
        output_dir = Path('evidence/probwin_tests')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_csv = output_dir / f'COMPARISON_THRESHOLDS_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        df_success.to_csv(output_csv, index=False)
        
        print(f"\n✅ Comparison saved to: {output_csv}")
        
        # Optimal threshold
        best = df_success.iloc[0]
        print("\n" + "=" * 100)
        print("🏆 OPTIMAL THRESHOLD")
        print("=" * 100)
        print(f"\nBest: Prob_Win >= {best['threshold']:.2f}")
        print(f"  • Avg Return:  {best['avg_return_weekly']:+.2f}%/week")
        print(f"  • Total PnL:   ${best['total_pnl']:+,.2f}")
        print(f"  • Win Rate:    {best['avg_win_rate']:.1f}%")
        print(f"  • Pos Weeks:   {best['positive_pct']:.1f}%")
        print(f"  • Sharpe:      {best['sharpe_approx']:.2f}")
    else:
        print("\n⚠️  No successful runs to compare")
        
    # Show all statuses
    print("\n" + "=" * 100)
    print("EXECUTION STATUS")
    print("=" * 100)
    for _, row in df.iterrows():
        print(f"  {row['threshold']:.2f}: {row['status']}")

print("\n" + "=" * 100)
print("DONE")
print("=" * 100)
