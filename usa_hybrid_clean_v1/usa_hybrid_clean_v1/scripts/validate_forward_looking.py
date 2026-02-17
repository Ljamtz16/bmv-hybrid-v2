"""
Validate forward-looking pipeline integrity:
1) No-leakage: features timestamp max <= T-1 (NY)
2) Coherence: |last_close - entry_price|/entry_price < 3% for all plan tickers
3) Traceability fields present in trade_plan.csv
4) Idempotency (optional): compare hash across two runs (skip here)
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

OK = "PASS"
FAIL = "FAIL"

def no_leakage_check() -> tuple[str, str]:
    try:
        ny = ZoneInfo("America/New_York")
        today = datetime.now(ny).date()
        t_minus_1 = pd.bdate_range(end=pd.Timestamp(today), periods=2, tz=ny).date[-2]
        p = Path('data/daily/features_enhanced_binary_targets.parquet')
        if not p.exists():
            return FAIL, "features_enhanced_binary_targets.parquet missing"
        df = pd.read_parquet(p)
        max_date_ny = pd.to_datetime(df['timestamp'], utc=True, errors='coerce').dt.tz_convert('America/New_York').dt.date.max()
        return (OK if max_date_ny <= t_minus_1 else FAIL,
                f"max_timestamp_NY={max_date_ny} | T-1={t_minus_1}")
    except Exception as e:
        return FAIL, f"exception: {e}"

def coherence_check(threshold: float = 0.03) -> tuple[str, str]:
    try:
        plan_p = Path('val/trade_plan.csv')
        prices_p = Path('data/us/ohlcv_us_daily.csv')
        if not plan_p.exists() or not prices_p.exists():
            return FAIL, "plan or daily prices missing"
        plan = pd.read_csv(plan_p)
        daily = pd.read_csv(prices_p)
        daily['date'] = pd.to_datetime(daily['date'])
        last_close = daily.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close']
        plan['last_close'] = plan['ticker'].map(last_close)
        plan['diff_pct'] = (plan['last_close'] - plan['entry_price'])/plan['entry_price']
        max_abs = float(plan['diff_pct'].abs().max())
        ok = max_abs < threshold
        # Short summary list
        rows = ", ".join(f"{r.ticker}:{r.diff_pct*100:.1f}%" for r in plan[['ticker','diff_pct']].itertuples(index=False))
        return (OK if ok else FAIL, f"max|diff|={max_abs*100:.2f}% (thr={threshold*100:.1f}%) | diffs=[{rows}]")
    except Exception as e:
        return FAIL, f"exception: {e}"

def traceability_check() -> tuple[str, str]:
    try:
        plan = pd.read_csv('val/trade_plan.csv')
        required = {'asof_date','model_hash','calibration_version','thresholds_applied'}
        present = required.issubset(set(plan.columns))
        return (OK if present else FAIL, f"present={present} missing={list(required - set(plan.columns))}")
    except Exception as e:
        return FAIL, f"exception: {e}"

if __name__ == "__main__":
    items = [
        ("No-leakage (T-1 cap)", no_leakage_check),
        ("Coherence (entry vs last close)", coherence_check),
        ("Traceability fields", traceability_check),
    ]
    print("== FORWARD-LOOKING VALIDATION ==")
    for name, fn in items:
        status, info = fn()
        print(f"- {name}: {status} | {info}")
