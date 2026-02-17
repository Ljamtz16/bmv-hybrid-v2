import pandas as pd
from src.execution.hybrid_v2 import atr_targets_daily

def test_targets_buy():
    idx = pd.date_range("2025-01-01", periods=20, freq="D")
    df = pd.DataFrame({
        "Open":10, "High":11, "Low":9, "Close":10, "Volume":100, "ATR_14":0.5
    }, index=idx)
    tp, sl, atr, close = atr_targets_daily(df, idx[-1], "BUY", 1.5, 1.0)
    assert abs(tp - 10.75) < 1e-9
    assert abs(sl - 9.5) < 1e-9
