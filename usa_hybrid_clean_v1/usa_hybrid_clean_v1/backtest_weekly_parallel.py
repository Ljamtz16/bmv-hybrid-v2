"""
Weekly backtest: Optimized version
Uses subprocess in parallel for speed
"""
import subprocess
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import multiprocessing as mp

# Generate week definitions
WEEKS = []
start_date = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)

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

def run_week(week):
    """Run backtest for single week"""
    week_label = f"{week['year']}_W{week['week']:02d}"
    output_dir = f"evidence/weekly_analysis/{week_label}"
    
    cmd = [
        './.venv/Scripts/python.exe',
        'backtest_comparative_modes.py',
        '--mode', 'probwin_only',
        '--pw_threshold', '0.55',
        '--start_date', week['start'],
        '--end_date', week['end'],
        '--output', output_dir
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            metrics_file = Path(output_dir) / 'metrics.json'
            if metrics_file.exists():
                with open(metrics_file) as f:
                    metrics = json.load(f)
                return {
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
                    'status': '✅'
                }
    except Exception as e:
        pass
    
    return None

print("=" * 100)
print(f"WEEKLY BACKTEST: ProbWin-Only (2024-2025)")
print("=" * 100)
print(f"Total weeks: {len(WEEKS)}")
print(f"Running in parallel with {mp.cpu_count()} workers...\n")

# Run in parallel
with mp.Pool(processes=min(4, mp.cpu_count())) as pool:
    results = list(filter(None, pool.imap_unordered(run_week, WEEKS)))

print(f"\n✅ Completed: {len(results)} / {len(WEEKS)} weeks")

if results:
    df = pd.DataFrame(results)
    df = df.sort_values(['year', 'week_num'])
    
    print("\n" + "=" * 100)
    print("SUMMARY STATISTICS")
    print("=" * 100)
    
    print(f"\nTotal weeks analyzed:     {len(df)}")
    print(f"Positive weeks:           {(df['return_pct'] > 0).sum()}")
    print(f"Negative weeks:           {(df['return_pct'] < 0).sum()}")
    print(f"Zero-trade weeks:         {(df['n_trades'] == 0).sum()}")
    
    print(f"\nReturn Statistics:")
    print(f"  Average:               {df['return_pct'].mean():+.2f}%")
    print(f"  Median:                {df['return_pct'].median():+.2f}%")
    print(f"  Std Dev:               {df['return_pct'].std():.2f}%")
    print(f"  Min:                   {df['return_pct'].min():+.2f}% ({df[df['return_pct']==df['return_pct'].min()]['week'].values[0]})")
    print(f"  Max:                   {df['return_pct'].max():+.2f}% ({df[df['return_pct']==df['return_pct'].max()]['week'].values[0]})")
    
    print(f"\nTrade Statistics:")
    print(f"  Total trades:          {int(df['n_trades'].sum())}")
    print(f"  Avg trades/week:       {df['n_trades'].mean():.1f}")
    print(f"  Median trades/week:    {df['n_trades'].median():.0f}")
    
    print(f"\nProfit Statistics:")
    print(f"  Total P&L:             ${df['total_pnl'].sum():+,.2f}")
    print(f"  Avg P&L/week:          ${df['total_pnl'].mean():+.2f}")
    print(f"  Best week P&L:         ${df['total_pnl'].max():+.2f} ({df[df['total_pnl']==df['total_pnl'].max()]['week'].values[0]})")
    print(f"  Worst week P&L:        ${df['total_pnl'].min():+.2f} ({df[df['total_pnl']==df['total_pnl'].min()]['week'].values[0]})")
    
    print(f"\nWin Rate Statistics:")
    print(f"  Average:               {df['win_rate'].mean():.1%}")
    print(f"  Median:                {df['win_rate'].median():.1%}")
    print(f"  Best week:             {df['win_rate'].max():.1%} ({df[df['win_rate']==df['win_rate'].max()]['week'].values[0]})")
    
    # By year
    print(f"\n" + "=" * 100)
    print("BY YEAR:")
    print("=" * 100)
    for year in sorted(df['year'].unique()):
        year_df = df[df['year'] == year]
        print(f"\n{year}:")
        print(f"  Weeks:      {len(year_df)}")
        print(f"  Avg Ret:    {year_df['return_pct'].mean():+.2f}% (std: {year_df['return_pct'].std():.2f}%)")
        print(f"  Total P&L:  ${year_df['total_pnl'].sum():+,.2f}")
        print(f"  Total Trades: {int(year_df['n_trades'].sum())}")
        print(f"  Avg WR:     {year_df['win_rate'].mean():.1%}")
    
    # Save results
    Path('evidence/weekly_analysis').mkdir(parents=True, exist_ok=True)
    df.to_csv('evidence/weekly_analysis/weekly_summary.csv', index=False)
    
    summary = {
        'total_weeks': len(df),
        'positive_weeks': int((df['return_pct'] > 0).sum()),
        'avg_return_pct': float(df['return_pct'].mean()),
        'total_pnl': float(df['total_pnl'].sum()),
        'total_trades': int(df['n_trades'].sum()),
        'avg_wr': float(df['win_rate'].mean()),
    }
    with open('evidence/weekly_analysis/weekly_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✅ Results saved to: evidence/weekly_analysis/")
    
    # Top/Bottom weeks
    print(f"\n" + "=" * 100)
    print("TOP 10 WEEKS:")
    print("=" * 100)
    top10 = df.nlargest(10, 'return_pct')[['week', 'return_pct', 'n_trades', 'win_rate', 'total_pnl']]
    print(top10.to_string(index=False))
    
    print(f"\n" + "=" * 100)
    print("BOTTOM 10 WEEKS:")
    print("=" * 100)
    bottom10 = df.nsmallest(10, 'return_pct')[['week', 'return_pct', 'n_trades', 'win_rate', 'total_pnl']]
    print(bottom10.to_string(index=False))

print("\n" + "=" * 100)
