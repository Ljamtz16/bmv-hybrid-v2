import pandas as pd

plan = pd.read_csv(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan_clean.csv', parse_dates=['date'])
print(f"dtype: {plan['date'].dtype}")
print(f"sample: {plan['date'].iloc[0]}")
if hasattr(plan['date'].dtype, 'tz'):
    print(f"tz: {plan['date'].dtype.tz}")
else:
    print("No tz attribute")

test_start = pd.Timestamp('2025-07-01')
print(f"test_start: {test_start}, tz: {test_start.tz}")
print(f"sample >= test_start works: ", end="")
try:
    result = plan['date'].iloc[0] >= test_start
    print(f"YES - {result}")
except Exception as e:
    print(f"NO - {e}")
