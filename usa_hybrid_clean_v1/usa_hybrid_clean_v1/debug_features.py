import pandas as pd
import numpy as np

df = pd.read_parquet('data/daily/features_enhanced_binary_targets.parquet')
print('Total cols:', len(df.columns))

exclude = ['timestamp', 'date', 'ticker', 'target', 'target_binary', 'target_ordinal',
           'open', 'high', 'low', 'close', 'volume', 'close_fwd', 'ret_fwd', 'thr_up', 'thr_dn',
           'atr_pct_w', 'k', 'regime', 'prev_close', 'hh_20', 'll_20', 'hh_60', 'll_60',
           'vol_avg_20', 'is_up', 'dow', 'day_of_month', 'atr_pct_p33', 'atr_pct_p66']

feat = [c for c in df.columns if c not in exclude]
print('Features after exclude:', len(feat))
print('First 20:', feat[:20])

# Check dtypes
for c in feat[:20]:
    dt = df[c].dtype
    if dt == 'object' or pd.api.types.is_string_dtype(dt):
        print(f"WARNING: {c} is non-numeric ({dt})")
