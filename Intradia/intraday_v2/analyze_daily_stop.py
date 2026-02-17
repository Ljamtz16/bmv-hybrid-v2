import pandas as pd

df = pd.read_csv(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv')
df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True)
df['date'] = df['entry_time'].dt.date

print("\n=== TRADES BY DATE (showing daily stop logic) ===\n")

# Analyze specific days where daily stop triggered
for date_str in ['2024-08-06', '2025-04-02']:
    subset = df[df['date'].astype(str) == date_str]
    if len(subset) > 0:
        print(f"\n{date_str}:")
        print(subset[['ticker', 'side', 'exit_reason', 'pnl', 'r_mult', 'daily_sl_count_at_entry', 'daily_r_at_entry']].to_string(index=False))

print("\n\n=== ALL BLOCKED TRADES ===\n")
blocked = df[df['exit_reason'].str.contains('DAILY_STOP', na=False)]
print(blocked[['entry_time', 'ticker', 'side', 'exit_reason', 'daily_sl_count_at_entry', 'daily_r_at_entry']].to_string(index=False))

print("\n\n=== SUMMARY ===")
print(f"Total trades in plan: {len(df)}")
print(f"Blocked by daily stop: {len(blocked)}")
print(f"Valid trades (TP/SL): {len(df[df['exit_reason'].isin(['TP', 'SL'])])}")
print(f"Block rate: {len(blocked)/len(df)*100:.1f}%")
