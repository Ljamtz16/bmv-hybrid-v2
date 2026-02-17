"""
Compare results from different prob_win threshold tests
"""
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

base_dir = Path('evidence/probwin_tests')
thresholds = [0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70]

print("="*100)
print("COMPARING PROB_WIN THRESHOLD RESULTS")
print("="*100)

results = []

for threshold in thresholds:
    dir_name = f'pw_{int(threshold*100)}'
    summary_file = base_dir / dir_name / 'weekly_summary.json'
    
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)
        
        results.append({
            'threshold': threshold,
            'avg_return_weekly': summary.get('overall_avg_return', 0),
            'total_pnl': summary.get('overall_total_pnl', 0),
            'total_trades': summary.get('overall_total_trades', 0),
            'avg_win_rate': summary.get('overall_avg_win_rate', 0) * 100,
            'positive_weeks': summary.get('positive_weeks', 0),
            'total_weeks': summary.get('total_weeks', 0),
            'positive_pct': summary.get('positive_weeks', 0) / summary.get('total_weeks', 1) * 100,
            'return_std': summary.get('return_std_dev', 0),
            'sharpe': summary.get('overall_avg_return', 0) / max(summary.get('return_std_dev', 1), 0.01),
            'best_week': summary.get('best_week', {}).get('return', 0),
            'worst_week': summary.get('worst_week', {}).get('return', 0)
        })
        print(f"[OK] Loaded: {dir_name}")
    else:
        print(f"[X] Missing: {dir_name}")

if results:
    df = pd.DataFrame(results)
    df = df.sort_values('avg_return_weekly', ascending=False)
    
    print("\n" + "="*100)
    print("RANKING BY AVERAGE WEEKLY RETURN")
    print("="*100)
    print("\n")
    print(df[['threshold', 'avg_return_weekly', 'total_trades', 'avg_win_rate', 'positive_pct', 'sharpe']].to_string(index=False))
    
    print("\n" + "="*100)
    print("DETAILED COMPARISON")
    print("="*100)
    
    for _, row in df.iterrows():
        print(f"\nProb_Win >= {row['threshold']:.2f}:")
        print(f"  Avg Return:      {row['avg_return_weekly']:+.2f}%/week ({row['avg_return_weekly']*52:+.1f}% annualized)")
        print(f"  Total PnL:       ${row['total_pnl']:+,.2f}")
        print(f"  Total Trades:    {row['total_trades']}")
        print(f"  Avg Win Rate:    {row['avg_win_rate']:.1f}%")
        print(f"  Positive Weeks:  {row['positive_weeks']}/{row['total_weeks']} ({row['positive_pct']:.1f}%)")
        print(f"  Std Dev:         {row['return_std']:.2f}%")
        print(f"  Sharpe (approx): {row['sharpe']:.2f}")
        print(f"  Best Week:       {row['best_week']:+.2f}%")
        print(f"  Worst Week:      {row['worst_week']:+.2f}%")
    
    # Save comparison
    output_file = base_dir / f'COMPARISON_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    df.to_csv(output_file, index=False)
    
    print(f"\n[OK] Comparison saved to: {output_file}")
    
    # Best threshold
    best = df.iloc[0]
    print("\n" + "="*100)
    print("OPTIMAL THRESHOLD")
    print("="*100)
    print(f"\nBest: Prob_Win >= {best['threshold']:.2f}")
    print(f"  Avg Return:  {best['avg_return_weekly']:+.2f}%/week")
    print(f"  Total PnL:   ${best['total_pnl']:+,.2f}")
    print(f"  Win Rate:    {best['avg_win_rate']:.1f}%")
    print(f"  Pos Weeks:   {best['positive_pct']:.1f}%")
    print(f"  Sharpe:      {best['sharpe']:.2f}")
else:
    print("\n[X] No results found")

print("\n" + "="*100)
