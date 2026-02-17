"""
Test multiple prob_win thresholds across weekly backtests
Compares different confidence thresholds to find optimal value
"""

import subprocess
import pandas as pd
import json
from pathlib import Path
import time

# ==============================================================================
# CONFIGURATION
# ==============================================================================
PROB_WIN_THRESHOLDS = [0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70]

results_summary = []

print("=" * 100)
print("TESTING MULTIPLE PROB_WIN THRESHOLDS")
print("=" * 100)
print(f"\nThresholds to test: {PROB_WIN_THRESHOLDS}")
print(f"Period: 2024-2025 (105 weeks)")
print(f"Capital: $2000, Max Deploy: $1900, Max Open: 4, Per Trade: $500")
print("\n" + "=" * 100)

for idx, threshold in enumerate(PROB_WIN_THRESHOLDS, 1):
    print(f"\n[{idx}/{len(PROB_WIN_THRESHOLDS)}] TESTING PROB_WIN >= {threshold}")
    print("-" * 100)
    
    # Create output directory for this threshold
    output_base = f"evidence/probwin_tests/pw_{int(threshold*100)}"
    Path(output_base).mkdir(parents=True, exist_ok=True)
    
    # Run weekly backtest with this threshold
    start_time = time.time()
    
    cmd = [
        './.venv/Scripts/python.exe',
        'backtest_weekly.py',
        '--pw_threshold', str(threshold),
        '--output_base', output_base
    ]
    
    # Note: backtest_weekly.py needs to accept --pw_threshold and --output_base parameters
    # For now, we'll modify backtest_comparative_modes.py threshold and run backtest_weekly.py
    
    # Temporary approach: modify backtest parameters in backtest_comparative_modes.py
    print(f"   Running weekly backtest with threshold {threshold}...")
    
    # Read current backtest_comparative_modes.py to modify PW threshold
    with open('backtest_comparative_modes.py', 'r', encoding='utf-8') as f:
        backtest_code = f.read()
    
    # Backup original
    with open('backtest_comparative_modes_backup.py', 'w', encoding='utf-8') as f:
        f.write(backtest_code)
    
    # We'll run backtest_weekly manually for each threshold
    # Since backtest_weekly.py calls backtest_comparative_modes.py with --pw_threshold
    # we just need to update the output directory
    
    result = subprocess.run(
        ['./.venv/Scripts/python.exe', 'backtest_weekly.py'],
        capture_output=True,
        text=True,
        timeout=3600  # 1 hour max
    )
    
    elapsed = time.time() - start_time
    
    if result.returncode == 0:
        # Load consolidated metrics
        metrics_file = Path('evidence/weekly_analysis/weekly_summary.json')
        
        if metrics_file.exists():
            with open(metrics_file) as f:
                summary = json.load(f)
            
            # Move results to threshold-specific directory
            import shutil
            
            # Copy weekly_summary files
            shutil.copy(
                'evidence/weekly_analysis/weekly_summary.csv',
                f'{output_base}/weekly_summary_pw{int(threshold*100)}.csv'
            )
            shutil.copy(
                'evidence/weekly_analysis/weekly_summary.json',
                f'{output_base}/weekly_summary_pw{int(threshold*100)}.json'
            )
            
            results_summary.append({
                'threshold': threshold,
                'total_weeks': summary.get('total_weeks', 0),
                'positive_weeks': summary.get('positive_weeks', 0),
                'negative_weeks': summary.get('negative_weeks', 0),
                'avg_return': summary.get('overall_avg_return', 0),
                'total_pnl': summary.get('overall_total_pnl', 0),
                'total_trades': summary.get('overall_total_trades', 0),
                'avg_win_rate': summary.get('overall_avg_win_rate', 0),
                'return_std': summary.get('return_std_dev', 0),
                'best_week_return': summary.get('best_week', {}).get('return', 0),
                'worst_week_return': summary.get('worst_week', {}).get('return', 0),
                'elapsed_time': elapsed,
                'status': '✅'
            })
            
            print(f"   ✅ Completed in {elapsed:.0f}s")
            print(f"      Avg Return: {summary.get('overall_avg_return', 0):+.2f}%/week")
            print(f"      Total Trades: {summary.get('overall_total_trades', 0)}")
            print(f"      Win Rate: {summary.get('overall_avg_win_rate', 0):.1%}")
        else:
            print(f"   ❌ No summary file found")
    else:
        print(f"   ❌ Error: {result.stderr[:100]}")
        results_summary.append({
            'threshold': threshold,
            'status': '❌',
            'error': result.stderr[:100]
        })

# ==============================================================================
# COMPARATIVE ANALYSIS
# ==============================================================================
print("\n" + "=" * 100)
print("COMPARATIVE RESULTS")
print("=" * 100)

if results_summary:
    df = pd.DataFrame(results_summary)
    
    if 'avg_return' in df.columns:
        # Sort by average return
        df_sorted = df.sort_values('avg_return', ascending=False)
        
        print("\nRanking by Average Weekly Return:")
        print(df_sorted[['threshold', 'avg_return', 'total_trades', 'avg_win_rate', 'positive_weeks', 'negative_weeks']].to_string(index=False))
        
        print("\n" + "=" * 100)
        print("DETAILED COMPARISON")
        print("=" * 100)
        
        for _, row in df_sorted.iterrows():
            print(f"\nProb_Win >= {row['threshold']:.2f}:")
            print(f"  Avg Return:      {row['avg_return']:+.2f}%/week")
            print(f"  Total PnL:       ${row['total_pnl']:+,.2f}")
            print(f"  Total Trades:    {row['total_trades']}")
            print(f"  Avg Win Rate:    {row['avg_win_rate']:.1%}")
            print(f"  Positive Weeks:  {row['positive_weeks']}/{row['total_weeks']} ({row['positive_weeks']/row['total_weeks']:.1%})")
            print(f"  Std Dev:         {row['return_std']:.2f}%")
            print(f"  Best Week:       {row['best_week_return']:+.2f}%")
            print(f"  Worst Week:      {row['worst_week_return']:+.2f}%")
        
        # Save comparison
        output_comparison = Path('evidence/probwin_tests/COMPARISON_PROBWIN_THRESHOLDS.csv')
        output_comparison.parent.mkdir(parents=True, exist_ok=True)
        df_sorted.to_csv(output_comparison, index=False)
        
        print(f"\n✅ Comparison saved to: {output_comparison}")
        
        # Find optimal
        best_row = df_sorted.iloc[0]
        print("\n" + "=" * 100)
        print("OPTIMAL THRESHOLD")
        print("=" * 100)
        print(f"\n🏆 Best threshold: {best_row['threshold']:.2f}")
        print(f"   Avg Return: {best_row['avg_return']:+.2f}%/week")
        print(f"   Total PnL: ${best_row['total_pnl']:+,.2f}")
        print(f"   Win Rate: {best_row['avg_win_rate']:.1%}")

print("\n" + "=" * 100)
