"""
Smoke test automatizado para validar garantías forward-looking del pipeline.
Exit code 0: PASS
Exit code 1: FAIL en una o más validaciones

Uso:
    python scripts/test_forward_looking.py [--allow-stale]
"""
import sys
import argparse
from pathlib import Path
import pandas as pd
from zoneinfo import ZoneInfo

def get_t_minus_1():
    """Retorna T-1 business day en America/New_York."""
    ny = ZoneInfo("America/New_York")
    t_minus_1 = pd.bdate_range(end=pd.Timestamp.now(tz=ny).normalize(), periods=2, tz=ny).date[-2]
    return t_minus_1

def normalize_date_ny(ts_col):
    """Convierte timestamp a date en timezone NY."""
    ts = pd.to_datetime(ts_col, utc=True, errors="coerce")
    ny = ZoneInfo("America/New_York")
    return ts.dt.tz_convert(ny).dt.date

def check_csv_freshness(t_minus_1, allow_stale=False):
    """Verifica que CSV tenga max(date_NY) == T-1."""
    csv_path = Path('data/us/ohlcv_us_daily.csv')
    if not csv_path.exists():
        return False, f"CSV no existe: {csv_path}", False
    
    df = pd.read_csv(csv_path)
    if 'date' not in df.columns:
        return False, f"CSV sin columna 'date'", False
    
    df['date_ny'] = normalize_date_ny(df['date'])
    max_date = df['date_ny'].max()
    days_behind = (t_minus_1 - max_date).days
    
    if days_behind > 0:
        msg = f"CSV max(date_NY)={max_date}, esperado {t_minus_1} ({days_behind} days behind)"
        if allow_stale and days_behind <= 2:
            return True, msg, True  # Pass with warning
        return False, msg, False
    
    return True, f"CSV fresh: max(date_NY)={max_date}", False

def check_features_freshness(t_minus_1, allow_stale=False):
    """Verifica que features tenga max(timestamp_NY) == T-1."""
    feat_path = Path('data/daily/features_daily_enhanced.parquet')
    if not feat_path.exists():
        return False, f"Features no existen: {feat_path}", False
    
    df = pd.read_parquet(feat_path)
    if 'timestamp' not in df.columns:
        return False, "Features sin columna 'timestamp'", False
    
    df['date_ny'] = normalize_date_ny(df['timestamp'])
    max_date = df['date_ny'].max()
    days_behind = (t_minus_1 - max_date).days
    
    if days_behind > 0:
        msg = f"Features max(timestamp_NY)={max_date}, esperado {t_minus_1} ({days_behind} days behind)"
        if allow_stale and days_behind <= 2:
            return True, msg, True  # Pass with warning
        return False, msg, False
    
    return True, f"Features fresh: max(timestamp_NY)={max_date}", False

def check_signals_purity(t_minus_1, allow_stale=False):
    """Verifica que signals contengan sólo filas de T-1 (o hasta 2 días atrás con --allow-stale)."""
    sig_path = Path('data/daily/signals_with_gates.parquet')
    if not sig_path.exists():
        return False, f"Signals no existen: {sig_path}", False
    
    df = pd.read_parquet(sig_path)
    if 'date' not in df.columns:
        return False, "Signals sin columna 'date'", False
    
    # La columna 'date' ya es datetime.date, no necesita conversión
    unique_dates = df['date'].unique()
    max_sig_date = max(unique_dates)
    days_behind = (t_minus_1 - max_sig_date).days
    
    if days_behind > 0:
        msg = f"Signals date={max_sig_date}, esperado {t_minus_1} ({days_behind} days behind)"
        if allow_stale and days_behind <= 2:
            return True, msg, True  # Pass with warning
        return False, msg, False
    
    if len(unique_dates) != 1 or unique_dates[0] != t_minus_1:
        return False, f"Signals contiene fechas {unique_dates}, esperado sólo [{t_minus_1}]", False
    
    return True, f"Signals purity: {len(df)} filas, todas de {t_minus_1}", False

def check_coherence(threshold=0.03):
    """Verifica que |entry_price - last_close| / last_close < threshold."""
    plan_path = Path('val/trade_plan.csv')
    csv_path = Path('data/us/ohlcv_us_daily.csv')
    
    if not plan_path.exists():
        return False, f"Plan no existe: {plan_path}", False
    if not csv_path.exists():
        return False, f"CSV no existe: {csv_path}", False
    
    plan = pd.read_csv(plan_path)
    csv = pd.read_csv(csv_path)
    
    if 'ticker' not in plan.columns or 'entry_price' not in plan.columns:
        return False, "Plan sin columnas ticker/entry_price", False
    
    csv['date_ny'] = normalize_date_ny(csv['date'])
    last = csv.groupby('ticker').tail(1)[['ticker', 'close']].rename(columns={'close': 'last_close'})
    
    merged = plan.merge(last, on='ticker', how='left')
    merged['diff_pct'] = abs(merged['entry_price'] - merged['last_close']) / merged['last_close']
    
    max_diff = merged['diff_pct'].max()
    violations = merged[merged['diff_pct'] > threshold]
    
    if len(violations) > 0:
        return False, f"Coherence violation: max_diff={max_diff:.2%} > {threshold:.1%}, {len(violations)} tickers afectados", False
    
    return True, f"Coherence OK: max_diff={max_diff:.2%} < {threshold:.1%}", False

def check_traceability():
    """Verifica presencia de campos de metadata en plan."""
    plan_path = Path('val/trade_plan.csv')
    if not plan_path.exists():
        return False, f"Plan no existe: {plan_path}", False
    
    plan = pd.read_csv(plan_path)
    required = ['asof_date', 'model_hash', 'calibration_version', 'thresholds_applied', 'data_freshness_date', 'entry_source']
    missing = [f for f in required if f not in plan.columns]
    
    if missing:
        return False, f"Metadata faltante: {missing}", False
    
    return True, f"Traceability OK: {len(required)} campos presentes", False

def main():
    parser = argparse.ArgumentParser(description="Valida garantías forward-looking del pipeline")
    parser.add_argument("--allow-stale", action="store_true",
                        help="Permite datos 1-2 días atrás (útil fines de semana)")
    args = parser.parse_args()
    
    t_minus_1 = get_t_minus_1()
    print(f"[TEST] Forward-looking validation para T-1={t_minus_1}")
    if args.allow_stale:
        print("[INFO] Running with --allow-stale (permite datos 1-2 días atrás)")
    print("="*60)
    
    checks = [
        ("CSV Freshness", check_csv_freshness, t_minus_1, args.allow_stale),
        ("Features Freshness", check_features_freshness, t_minus_1, args.allow_stale),
        ("Signals Purity", check_signals_purity, t_minus_1, args.allow_stale),
        ("Coherence (<3%)", check_coherence, None, None),
        ("Traceability", check_traceability, None, None)
    ]
    
    results = []
    warnings = []
    for name, func, arg, allow_stale_arg in checks:
        if arg is not None and allow_stale_arg is not None:
            status, msg, is_warning = func(arg, allow_stale_arg)
        elif arg is not None:
            status, msg, is_warning = func(arg)
        else:
            status, msg, is_warning = func()
        
        results.append((name, status, msg))
        if is_warning:
            warnings.append(name)
            status_str = "[WARN]"
        else:
            status_str = "[PASS]" if status else "[FAIL]"
        print(f"{status_str} | {name:20s} | {msg}")
    
    print("="*60)
    failures = [r for r in results if not r[1]]
    
    if failures:
        print(f"[FAIL] {len(failures)}/{len(checks)} validaciones fallaron")
        sys.exit(1)
    else:
        if warnings:
            print(f"[PASS] {len(checks)}/{len(checks)} validaciones exitosas ({len(warnings)} warnings)")
        else:
            print(f"[PASS] {len(checks)}/{len(checks)} validaciones exitosas")
        sys.exit(0)

if __name__ == "__main__":
    main()
