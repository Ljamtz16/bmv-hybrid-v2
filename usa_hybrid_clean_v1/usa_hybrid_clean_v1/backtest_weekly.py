"""
Weekly backtest analysis: ProbWin-only for each week of 2024-2025
Tests robustness and consistency across time
"""

import subprocess
import json
import pandas as pd
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# ==============================================================================
# PARSE ARGUMENTS
# ==============================================================================
parser = argparse.ArgumentParser(description='Weekly backtest with configurable prob_win threshold')
parser.add_argument('--pw_threshold', type=float, default=0.55, help='Prob_win threshold (default: 0.55)')
parser.add_argument('--output_base', type=str, default='evidence/weekly_analysis', help='Base output directory')
args = parser.parse_args()

PW_THRESHOLD = args.pw_threshold
OUTPUT_BASE = args.output_base

# ==============================================================================
# CONFIGURATION
# ==============================================================================
WEEKS = []
start_date = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)

# Generate weeks
current = start_date
week_num = 1
while current <= end_date:
    week_start = current
    week_end = min(current + timedelta(days=6), end_date)
    WEEKS.append({
        'week': week_num,
        'year': current.year,
        'start': week_start.strftime('%Y-%m-%d'),
        'end': week_end.strftime('%Y-%m-%d'),
    })
    current = week_end + timedelta(days=1)
    week_num += 1

print("=" * 100)
print(f"WEEKLY BACKTEST ANALYSIS: ProbWin-Only")
print("=" * 100)
print(f"\nProb_Win Threshold: {PW_THRESHOLD}")
print(f"Output Base: {OUTPUT_BASE}")
print(f"Total weeks to test: {len(WEEKS)}")
print(f"Period: {WEEKS[0]['start']} to {WEEKS[-1]['end']}")

results = []

for idx, week in enumerate(WEEKS, 1):
    week_label = f"{week['year']}_W{week['week']:02d}"
    output_dir = f"{OUTPUT_BASE}/{week_label}"
    
    print(f"\n[{idx:3d}/{len(WEEKS)}] {week_label}: {week['start']} to {week['end']}", end=" ... ", flush=True)
    
    # Run backtest for this week
    cmd = [
        './.venv/Scripts/python.exe',
        'backtest_comparative_modes.py',
        '--mode', 'probwin_only',
        '--pw_threshold', str(PW_THRESHOLD),
        '--start_date', week['start'],
        '--end_date', week['end'],
        '--output', output_dir
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            # Load metrics
            metrics_file = Path(output_dir) / 'metrics.json'
            if metrics_file.exists():
                with open(metrics_file) as f:
                    metrics = json.load(f)
                
                results.append({
                    'week': week_label,
                    'start_date': week['start'],
                    'end_date': week['end'],
                    'year': week['year'],
                    'week_num': week['week'],
                    'return_pct': metrics.get('return_pct', 0),
                    'total_pnl': metrics.get('total_pnl', 0),
                    'n_trades': metrics.get('n_trades', 0),
                    'win_rate': metrics.get('win_rate', 0),
                    'profit_factor': metrics.get('profit_factor', 0),
                    'avg_pnl_per_trade': metrics.get('avg_pnl_per_trade', 0),
                    'final_equity': metrics.get('final_equity', 1000),
                    'status': 'OK'
                })
                print(f"[OK] {metrics.get('return_pct', 0):.1f}% | {metrics.get('n_trades', 0):3d} trades | WR {metrics.get('win_rate', 0):.1%}")
            else:
                print("[X] No metrics file")
        else:
            print(f"[X] Error code {result.returncode}")
            if result.stderr:
                print(f"    STDERR: {result.stderr[:200]}")
            if result.stdout:
                print(f"    STDOUT: {result.stdout[:200]}")
    except Exception as e:
        print(f"[X] Exception: {str(e)[:100]}")

# ==============================================================================
# SUMMARY ANALYSIS
# ==============================================================================
print("\n" + "=" * 100)
print("WEEKLY SUMMARY")
print("=" * 100)

if results:
    df = pd.DataFrame(results)
    
    # Summary table
    print("\nAll Weeks:")
    print(df[['week', 'start_date', 'end_date', 'return_pct', 'n_trades', 'win_rate', 'profit_factor', 'avg_pnl_per_trade']].to_string(index=False))
    
    # Statistics by year
    print("\n" + "=" * 100)
    print("BY YEAR:")
    print("=" * 100)
    for year in sorted(df['year'].unique()):
        year_df = df[df['year'] == year]
        avg_return = year_df['return_pct'].mean()
        total_pnl = year_df['total_pnl'].sum()
        total_trades = year_df['n_trades'].sum()
        avg_wr = year_df['win_rate'].mean()
        
        print(f"\n{year}:")
        print(f"  Weeks:        {len(year_df)}")
        print(f"  Avg Return:   {avg_return:+.2f}% (std: {year_df['return_pct'].std():.2f}%)")
        print(f"  Total P&L:    ${total_pnl:+,.2f}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Avg WR:       {avg_wr:.1%}")
    
    # Overall statistics
    print("\n" + "=" * 100)
    print("OVERALL STATISTICS (2024-2025):")
    print("=" * 100)
    
    overall_return = df['return_pct'].mean()
    overall_pnl = df['total_pnl'].sum()
    overall_trades = df['n_trades'].sum()
    overall_wr = df['win_rate'].mean()
    
    print(f"\nWeeks with positive return:   {(df['return_pct'] > 0).sum()} / {len(df)} ({(df['return_pct'] > 0).sum() / len(df):.1%})")
    print(f"Weeks with negative return:   {(df['return_pct'] < 0).sum()} / {len(df)} ({(df['return_pct'] < 0).sum() / len(df):.1%})")
    print(f"Weeks with zero trades:       {(df['n_trades'] == 0).sum()} / {len(df)}")
    
    print(f"\nReturn Distribution:")
    print(f"  Average:    {overall_return:+.2f}%")
    print(f"  Median:     {df['return_pct'].median():+.2f}%")
    print(f"  Min:        {df['return_pct'].min():+.2f}%")
    print(f"  Max:        {df['return_pct'].max():+.2f}%")
    print(f"  Std Dev:    {df['return_pct'].std():.2f}%")
    
    print(f"\nTrades Distribution:")
    print(f"  Total:      {overall_trades}")
    print(f"  Average:    {df['n_trades'].mean():.1f}/week")
    print(f"  Median:     {df['n_trades'].median():.0f}/week")
    print(f"  Max week:   {df['n_trades'].max()} ({df[df['n_trades'] == df['n_trades'].max()]['week'].values[0]})")
    print(f"  Min week:   {df['n_trades'].min()} ({df[df['n_trades'] == df['n_trades'].min()]['week'].values[0]})")
    
    print(f"\nProfit Distribution:")
    print(f"  Total P&L:  ${overall_pnl:+,.2f}")
    print(f"  Avg P&L:    ${df['total_pnl'].mean():+.2f}/week")
    print(f"  Max P&L:    ${df['total_pnl'].max():+.2f} ({df[df['total_pnl'] == df['total_pnl'].max()]['week'].values[0]})")
    print(f"  Min P&L:    ${df['total_pnl'].min():+.2f} ({df[df['total_pnl'] == df['total_pnl'].min()]['week'].values[0]})")
    
    print(f"\nWin Rate Distribution:")
    print(f"  Average:    {overall_wr:.1%}")
    print(f"  Median:     {df['win_rate'].median():.1%}")
    print(f"  Best week:  {df['win_rate'].max():.1%} ({df[df['win_rate'] == df['win_rate'].max()]['week'].values[0]})")
    print(f"  Worst week: {df['win_rate'].min():.1%} ({df[df['win_rate'] == df['win_rate'].min()]['week'].values[0]})")
    
    # Top/Bottom weeks
    print("\n" + "=" * 100)
    print("TOP 5 WEEKS BY RETURN:")
    print("=" * 100)
    top5 = df.nlargest(5, 'return_pct')[['week', 'return_pct', 'n_trades', 'win_rate', 'total_pnl']]
    print(top5.to_string(index=False))
    
    print("\n" + "=" * 100)
    print("BOTTOM 5 WEEKS BY RETURN:")
    print("=" * 100)
    bottom5 = df.nsmallest(5, 'return_pct')[['week', 'return_pct', 'n_trades', 'win_rate', 'total_pnl']]
    print(bottom5.to_string(index=False))
    
    # Save detailed CSV
    output_csv = Path(f'{OUTPUT_BASE}/weekly_summary.csv')
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"\n[OK] Detailed results saved to: {output_csv}")
    
    # Save summary JSON
    summary = {
        'period': '2024-2025',
        'mode': 'probwin_only',
        'pw_threshold': PW_THRESHOLD,
        'total_weeks': len(df),
        'positive_weeks': int((df['return_pct'] > 0).sum()),
        'negative_weeks': int((df['return_pct'] < 0).sum()),
        'zero_trade_weeks': int((df['n_trades'] == 0).sum()),
        'overall_avg_return': float(overall_return),
        'overall_total_pnl': float(overall_pnl),
        'overall_total_trades': int(overall_trades),
        'overall_avg_win_rate': float(overall_wr),
        'return_std_dev': float(df['return_pct'].std()),
        'best_week': {
            'week': df.loc[df['return_pct'].idxmax(), 'week'],
            'return': float(df['return_pct'].max()),
            'pnl': float(df.loc[df['return_pct'].idxmax(), 'total_pnl'])
        },
        'worst_week': {
            'week': df.loc[df['return_pct'].idxmin(), 'week'],
            'return': float(df['return_pct'].min()),
            'pnl': float(df.loc[df['return_pct'].idxmin(), 'total_pnl'])
        }
    }
    
    output_json = Path(f'{OUTPUT_BASE}/weekly_summary.json')
    with open(output_json, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"[OK] Summary saved to: {output_json}")

print("\n" + "=" * 100)
