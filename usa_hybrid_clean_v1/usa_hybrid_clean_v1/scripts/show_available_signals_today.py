import pandas as pd
from datetime import datetime

fp = 'reports/forecast/2025-11/forecast_with_patterns_tth.csv'
df = pd.read_csv(fp)
if 'date' in df.columns:
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
latest = df['date'].max()
df_today = df[df['date']==latest].copy()

print(f"Señales en fecha más reciente ({latest.date()}): {len(df_today)}")
print(f"- Con gate_ok=1: {len(df_today[df_today.get('gate_ok',1)==1])}")

cols = [c for c in ['ticker','prob_win','abs_y_hat','etth_first_event','p_tp_before_sl','tth_score'] if c in df_today.columns]
print(df_today.sort_values(cols, ascending=[False, False, True, False, False]).head(20)[['ticker','prob_win','abs_y_hat','etth_first_event','p_tp_before_sl']].to_string(index=False))
