"""
Quick single threshold test - Run manually for each threshold
"""
import subprocess
import sys
from pathlib import Path
import json

if len(sys.argv) < 2:
    print("Usage: python test_single_threshold.py <threshold>")
    print("Example: python test_single_threshold.py 0.55")
    sys.exit(1)

threshold = float(sys.argv[1])
output_dir = f"evidence/probwin_tests/pw_{int(threshold*100)}"

print("="*100)
print(f"TESTING PROB_WIN >= {threshold}")
print("="*100)
print(f"\nOutput: {output_dir}/")
print(f"Running 105 weekly backtests...")
print("\n" + "="*100 + "\n")

# Run backtest
cmd = [
    './.venv/Scripts/python.exe',
    'backtest_weekly.py',
    '--pw_threshold', str(threshold),
    '--output_base', output_dir
]

result = subprocess.run(cmd)

if result.returncode == 0:
    # Load and display summary
    summary_file = Path(f'{output_dir}/weekly_summary.json')
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)
        
        print("\n" + "="*100)
        print(f"RESULTS FOR PROB_WIN >= {threshold}")
        print("="*100)
        print(f"\nAvg Return:     {summary.get('overall_avg_return', 0):+.2f}%/week")
        print(f"Total PnL:      ${summary.get('overall_total_pnl', 0):+,.2f}")
        print(f"Total Trades:   {summary.get('overall_total_trades', 0)}")
        print(f"Avg Win Rate:   {summary.get('overall_avg_win_rate', 0):.1%}")
        print(f"Positive Weeks: {summary.get('positive_weeks', 0)}/{summary.get('total_weeks', 0)}")
        print(f"Std Dev:        {summary.get('return_std_dev', 0):.2f}%")
        print(f"\nBest Week:      {summary['best_week']['return']:+.2f}%")
        print(f"Worst Week:     {summary['worst_week']['return']:+.2f}%")
        print("\n" + "="*100)
    else:
        print(f"\n[X] Summary file not found: {summary_file}")
else:
    print(f"\n[X] Backtest failed with exit code {result.returncode}")
