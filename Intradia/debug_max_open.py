import pandas as pd

trades = pd.read_csv('intraday_v2/artifacts/baseline_v1/trades.csv')
trades_use = trades[trades.get('allowed', True) == True].copy()
trades_use = trades_use.sort_values('entry_time').reset_index(drop=True)

print(f"Total trades: {len(trades)}")
print(f"Allowed trades: {len(trades_use)}")

max_open = 2
open_positions = []
max_open_seen = 0
violating_rows = []

for idx, row in trades_use.iterrows():
    open_positions = [p for p in open_positions if p['exit_time'] > row.entry_time]
    open_positions.append({
        'entry_time': row.entry_time,
        'exit_time': row.exit_time,
        'ticker': row.ticker,
    })
    if len(open_positions) > max_open:
        print(f"idx={idx}, ticker={row.ticker}, entry_time={row.entry_time}, exit_time={row.exit_time}, open_count={len(open_positions)}")
        violating_rows.append(idx)
    max_open_seen = max(max_open_seen, len(open_positions))

print(f"\nMax open seen: {max_open_seen}")
print(f"Violating row indices: {violating_rows[:5]}")
