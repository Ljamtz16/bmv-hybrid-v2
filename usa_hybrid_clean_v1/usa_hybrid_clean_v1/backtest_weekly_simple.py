"""
Weekly backtest: Sequential version
Simpler, no multiprocessing issues
"""
import subprocess
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# Generate weeks
weeks = []
current = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)
week_num = 1

while current <= end_date:
    week_start = current
    week_end = min(current + timedelta(days=6), end_date)
    weeks.append({
        'week': week_num,
        'year': current.year,
        'start': week_start.strftime('%Y-%m-%d'),
        'end': week_end.strftime('%Y-%m-%d'),
    })
    current = week_end + timedelta(days=1)
    week_num += 1

print("=" * 100)
print(f"WEEKLY BACKTEST: ProbWin-Only (2024-2025)")
print("=" * 100)
print(f"Total weeks: {len(weeks)}\n")

results = []
for idx, week in enumerate(weeks, 1):
    week_label = f"{week['year']}_W{week['week']:02d}"
    output_dir = f"evidence/weekly_analysis/{week_label}"
    
    print(f"[{idx:3d}/{len(weeks)}] {week_label}: {week['start']} to {week['end']}", end=" ... ", flush=True)
    
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
                })
                ret = metrics.get('return_pct', 0)
                tr = metrics.get('n_trades', 0)
                wr = metrics.get('win_rate', 0)
                print(f"✅ {ret:+.2f}% | {tr:3d} trades | WR {wr:.1%}")
            else:
                print("❌")
        else:
            print("❌")
    except Exception as e:
        print(f"❌ {str(e)[:30]}")

print("\n" + "=" * 100)
if results:
    df = pd.DataFrame(results)
    df = df.sort_values(['year', 'week_num'])
    
    print("SUMMARY (2024-2025)")
    print("=" * 100)
    print(f"\nWeeks analyzed:           {len(df)}")
    print(f"Positive weeks:           {(df['return_pct'] > 0).sum()}")
    print(f"Negative weeks:           {(df['return_pct'] < 0).sum()}")
    print(f"Zero-trade weeks:         {(df['n_trades'] == 0).sum()}")
    
    print(f"\nReturn:")
    print(f"  Average:                {df['return_pct'].mean():+.2f}%")
    print(f"  Std Dev:                {df['return_pct'].std():.2f}%")
    print(f"  Min:                    {df['return_pct'].min():+.2f}%")
    print(f"  Max:                    {df['return_pct'].max():+.2f}%")
    
    print(f"\nTrades:")
    print(f"  Total:                  {int(df['n_trades'].sum())}")
    print(f"  Avg/week:               {df['n_trades'].mean():.1f}")
    
    print(f"\nProfit:")
    print(f"  Total P&L:              ${df['total_pnl'].sum():+,.2f}")
    print(f"  Avg P&L/week:           ${df['total_pnl'].mean():+.2f}")
    
    print(f"\nWin Rate:")
    print(f"  Average:                {df['win_rate'].mean():.1%}")
    
    # By year
    print(f"\n" + "=" * 100)
    for year in sorted(df['year'].unique()):
        year_df = df[df['year'] == year]
        print(f"\n{year}:")
        print(f"  Weeks: {len(year_df)} | Avg Return: {year_df['return_pct'].mean():+.2f}% | Total P&L: ${year_df['total_pnl'].sum():+,.2f} | Total Trades: {int(year_df['n_trades'].sum())} | Avg WR: {year_df['win_rate'].mean():.1%}")
    
    # Top/Bottom
    print(f"\n" + "=" * 100)
    print("TOP 5 WEEKS:")
    print("=" * 100)
    print(df.nlargest(5, 'return_pct')[['week', 'return_pct', 'n_trades', 'total_pnl']].to_string(index=False))
    
    print(f"\n" + "=" * 100)
    print("BOTTOM 5 WEEKS:")
    print("=" * 100)
    print(df.nsmallest(5, 'return_pct')[['week', 'return_pct', 'n_trades', 'total_pnl']].to_string(index=False))
    
    # Save
    Path('evidence/weekly_analysis').mkdir(parents=True, exist_ok=True)
    df.to_csv('evidence/weekly_analysis/weekly_summary.csv', index=False)
    print(f"\n✅ Saved: evidence/weekly_analysis/weekly_summary.csv")

print("=" * 100)
