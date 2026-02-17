import pandas as pd

trades = pd.read_csv('intraday_v2/artifacts/baseline_v1/trades.csv')

# Allowed trades with probwin score
allowed_with_probwin = trades[(trades['allowed'] == True) & (trades['probwin'].notna())]
print("Allowed trades with ProbWin score (first 3):")
print(allowed_with_probwin[['ticker', 'entry_time', 'allowed', 'probwin', 'threshold', 'pnl']].head(3).to_string())

print("\n" + "="*80 + "\n")

# Blocked by PROBWIN_LOW
blocked_probwin = trades[trades['block_reason'] == 'PROBWIN_LOW']
print(f"Blocked by PROBWIN_LOW: {len(blocked_probwin)} trades")
print("\nDistribution of ProbWin scores (blocked):")
print(blocked_probwin['probwin'].describe())

print("\n" + "="*80 + "\n")

# Compare: allowed vs blocked scores
if len(allowed_with_probwin) > 0:
    print("Mean ProbWin score (allowed): {:.4f}".format(allowed_with_probwin['probwin'].mean()))
print("Mean ProbWin score (blocked): {:.4f}".format(blocked_probwin['probwin'].mean()))
print("Threshold: 0.55")
