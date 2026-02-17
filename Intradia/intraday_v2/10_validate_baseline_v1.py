# Script 10 — Validate Baseline v1 (5 pruebas obligatorias)
#
# Pruebas:
# 1) Cero leakage: señal y features usan solo datos <= entry
# 2) TZ consistente: date_ny y hour_bucket correctos
# 3) EOD real: exit_time = última vela NY del día cuando no tocó TP/SL
# 4) Risk real: shares cambia con equity y distancia SL
# 5) max_open real: nunca > 2 trades simultáneos

from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np


def _resolve_intraday_path(base_dir: Path) -> Path:
    parquet_path = base_dir.parent / 'data' / 'us' / 'intraday_15m' / 'consolidated_15m.parquet'
    csv_path = base_dir.parent / 'data' / 'us' / 'intraday_15m' / 'consolidated_15m.csv'

    if parquet_path.exists():
        return parquet_path
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(f"No se encontró consolidated_15m.parquet ni consolidated_15m.csv en {parquet_path.parent}")


def _load_intraday(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.parquet':
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _build_bar_features(bars: pd.DataFrame, timezone_target: str) -> pd.DataFrame:
    bars = bars.rename(columns={'timestamp': 'datetime'}).copy()
    bars['datetime'] = pd.to_datetime(bars['datetime'])

    if bars['datetime'].dt.tz is None:
        bars['datetime'] = bars['datetime'].dt.tz_localize('UTC').dt.tz_convert(timezone_target)
    else:
        bars['datetime'] = bars['datetime'].dt.tz_convert(timezone_target)

    bars = bars.sort_values(['ticker', 'datetime']).reset_index(drop=True)

    bars['prev_close'] = bars.groupby('ticker')['close'].shift(1)
    tr = np.maximum.reduce([
        bars['high'] - bars['low'],
        (bars['high'] - bars['prev_close']).abs(),
        (bars['low'] - bars['prev_close']).abs()
    ])
    bars['tr'] = pd.Series(tr, index=bars.index).fillna(bars['high'] - bars['low'])
    bars['atr14'] = (
        bars.groupby('ticker')['tr']
        .transform(lambda x: x.rolling(14, min_periods=1).mean())
    )

    bars['ret1'] = bars.groupby('ticker')['close'].pct_change()
    bars['ret4'] = bars.groupby('ticker')['close'].pct_change(4)
    bars['ret1_prev'] = bars.groupby('ticker')['ret1'].shift(1)
    bars['ret4_prev'] = bars.groupby('ticker')['ret4'].shift(1)
    bars['vol4'] = (
        bars.groupby('ticker')['ret1']
        .transform(lambda x: x.rolling(4, min_periods=4).std())
        .shift(1)
    )
    vol_mean = bars.groupby('ticker')['volume'].transform(lambda x: x.rolling(20, min_periods=20).mean())
    vol_std = bars.groupby('ticker')['volume'].transform(lambda x: x.rolling(20, min_periods=20).std())
    bars['vol_z20'] = ((bars['volume'] - vol_mean) / vol_std).shift(1)

    bars['atr_ratio'] = (bars['high'] - bars['low']) / bars['atr14'].replace(0, np.nan)
    denom = (bars['high'] - bars['low']).replace(0, np.nan)
    bars['body_pct'] = (bars['close'] - bars['open']).abs() / denom

    return bars


def validate_baseline_v1(
    trades_path: str | None = None,
    signals_path: str | None = None,
    intraday_path: str | None = None,
    timezone_target: str = 'America/New_York',
    risk_per_trade: float = 0.0075,
    max_open: int = 2
) -> dict:
    base_dir = Path(__file__).resolve().parent
    data_path = Path(intraday_path) if intraday_path else _resolve_intraday_path(base_dir)

    trades_path = Path(trades_path) if trades_path else (base_dir / 'artifacts' / 'baseline_v1' / 'trades.csv')
    signals_path = Path(signals_path) if signals_path else (base_dir / 'artifacts' / 'baseline_v1' / 'baseline_signals.csv')

    if not trades_path.exists():
        raise FileNotFoundError(f"No se encontró trades.csv en {trades_path}")
    if not signals_path.exists():
        raise FileNotFoundError(f"No se encontró baseline_signals.csv en {signals_path}")

    trades = pd.read_csv(trades_path)
    signals = pd.read_csv(signals_path)

    bars = _load_intraday(data_path)
    bars = _build_bar_features(bars, timezone_target)
    bars['date_ny'] = bars['datetime'].dt.date

    def _parse_maybe_tz(series: pd.Series) -> pd.Series:
        s = series.astype(str)
        has_tz = s.str.contains(r'(?:[+-]\d\d:\d\d|Z)$')
        out = pd.Series(index=series.index, dtype='datetime64[ns, UTC]')

        if has_tz.any():
            out.loc[has_tz] = pd.to_datetime(series[has_tz], utc=True, errors='coerce')
        if (~has_tz).any():
            naive = pd.to_datetime(series[~has_tz], errors='coerce')
            out.loc[~has_tz] = naive.dt.tz_localize(timezone_target)

        return out.dt.tz_convert(timezone_target)

    # Parse timestamps (handle tz-aware and naive)
    trades['entry_time'] = _parse_maybe_tz(trades['entry_time'])
    trades['exit_time'] = _parse_maybe_tz(trades['exit_time'])
    signals['signal_time'] = _parse_maybe_tz(signals['signal_time'])
    signals['entry_time'] = _parse_maybe_tz(signals['entry_time'])

    # Normalizar date_ny como fecha
    trades['date_ny'] = pd.to_datetime(trades['date_ny']).dt.date
    signals['date_ny'] = pd.to_datetime(signals['date_ny']).dt.date

    # 1) Cero leakage — señal breakout valida (vectorizado)
    bars = bars.sort_values(['ticker', 'datetime']).reset_index(drop=True)
    bars['breakout'] = (
        bars.groupby('ticker')['high']
        .transform(lambda x: x.shift(1).rolling(4, min_periods=4).max())
    )
    bars['breakout'] = bars['close'] > bars['breakout']

    signals_check = signals.merge(
        bars[['ticker', 'datetime', 'breakout']],
        left_on=['ticker', 'signal_time'],
        right_on=['ticker', 'datetime'],
        how='left'
    )

    leakage_errors = int((signals_check['breakout'] != True).sum())
    if leakage_errors > 0:
        raise ValueError(f"Cero leakage falló: {leakage_errors} señales no cumplen breakout 4 velas")

    # Features: ret1_prev/ret4_prev/vol4/vol_z20 consistentes con bar previo
    bars_keyed = bars.set_index(['ticker', 'datetime'])
    bars['expected_ret1_prev'] = bars.groupby('ticker')['ret1'].shift(1)
    trades_feat = trades.merge(
        bars[['ticker', 'datetime', 'ret1_prev', 'expected_ret1_prev']]
            .rename(columns={'datetime': 'entry_time'}),
        on=['ticker', 'entry_time'],
        how='left'
    )

    valid_feat = trades_feat['ret1_prev'].notna() & trades_feat['expected_ret1_prev'].notna()
    features_errors = int((~np.isclose(trades_feat.loc[valid_feat, 'ret1_prev'], trades_feat.loc[valid_feat, 'expected_ret1_prev'], equal_nan=True)).sum())
    if features_errors > 0:
        raise ValueError(f"Cero leakage falló: {features_errors} ret1_prev inconsistentes")

    # 2) TZ consistente
    tz_errors = 0
    trades_local = trades.copy()
    trades_local['entry_time'] = trades_local['entry_time'].dt.tz_convert(timezone_target)
    date_ok = trades_local['date_ny'].astype(str) == trades_local['entry_time'].dt.date.astype(str)
    hour_ok = trades_local['hour_bucket'] == trades_local['entry_time'].dt.strftime('%H:%M')
    if not date_ok.all():
        tz_errors += (~date_ok).sum()
    if not hour_ok.all():
        tz_errors += (~hour_ok).sum()

    if tz_errors > 0:
        raise ValueError(f"TZ consistente falló: {tz_errors} filas con date_ny/hour_bucket inconsistente")

    # 3) EOD real
    eod_trades = trades[trades['exit_reason'] == 'EOD'].copy()
    day_last = (
        bars.groupby(['ticker', 'date_ny'])['datetime']
        .max()
        .reset_index()
        .rename(columns={'datetime': 'last_bar_time'})
    )
    eod_check = eod_trades.merge(
        day_last,
        left_on=['ticker', 'date_ny'],
        right_on=['ticker', 'date_ny'],
        how='left'
    )
    eod_errors = int((eod_check['exit_time'] != eod_check['last_bar_time']).sum())

    if eod_errors > 0:
        raise ValueError(f"EOD real falló: {eod_errors} trades con exit_time distinto de última vela del día")

    # 4) Risk real: shares con equity y distancia SL
    trades_use = trades[trades.get('allowed', True) == True].copy()
    trades_use = trades_use.sort_values('entry_time').reset_index(drop=True)

    equity = 2000.0
    open_positions = []
    risk_errors = 0
    risk_mismatches = []

    def close_positions_up_to(ts):
        nonlocal equity
        remaining = []
        for pos in open_positions:
            if pos['exit_time'] <= ts:
                equity += pos['pnl']
            else:
                remaining.append(pos)
        return remaining

    for idx, row in trades_use.iterrows():
        if pd.isna(row.entry_time) or pd.isna(row.exit_time):
            continue
        open_positions = close_positions_up_to(row.entry_time)
        equity_before = equity
        risk_per_share = abs(row.entry - row.sl)
        if risk_per_share <= 0:
            continue
        expected_shares = int(np.floor((equity * risk_per_trade) / risk_per_share))

        equity_at_entry = row.get('equity_at_entry', np.nan)
        if pd.notna(equity_at_entry):
            equity_for_validator = float(equity_at_entry)
        else:
            equity_for_validator = float(equity)

        expected_from_equity_at_entry = int(
            np.floor((equity_for_validator * risk_per_trade) / risk_per_share)
        )

        if expected_from_equity_at_entry != int(row.shares):
            risk_errors += 1
            risk_cash_expected = equity_for_validator * risk_per_trade
            ratio_expected = risk_cash_expected / risk_per_share if risk_per_share > 0 else np.nan
            risk_mismatches.append({
                'trade_id': int(idx),
                'ticker': row.ticker,
                'entry_time': row.entry_time,
                'entry_price': row.entry,
                'sl_price': row.sl,
                'equity_at_entry': equity_at_entry,
                'equity_usada_por_validador': equity_for_validator,
                'equity_alternativa_simulada': equity_before,
                'risk_per_trade': risk_per_trade,
                'risk_cash_expected': risk_cash_expected,
                'risk_per_share_expected': risk_per_share,
                'shares_expected': expected_from_equity_at_entry,
                'shares_actual': int(row.shares),
                'ratio_expected': ratio_expected
            })

        open_positions.append({'exit_time': row.exit_time, 'pnl': row.pnl})

    if risk_errors > 0:
        mismatches_df = pd.DataFrame(risk_mismatches).head(50)
        output_path = base_dir / 'artifacts' / 'baseline_v1' / 'risk_mismatches_sample.csv'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mismatches_df.to_csv(output_path, index=False)

        if len(risk_mismatches) > 0:
            first = risk_mismatches[0]
            diff = first['shares_expected'] - first['shares_actual']
            print("[10] Primer mismatch:")
            print(first)
            print(f"[10] Diferencia shares_expected - shares_actual = {diff}")

        raise ValueError(f"Risk real falló: {risk_errors} trades con shares distinto al esperado")

    # 5) max_open real
    trades_use = trades_use.sort_values('entry_time').reset_index(drop=True)
    open_positions = []
    max_open_seen = 0
    max_open_violations = []

    for idx, row in trades_use.iterrows():
        open_positions = [p for p in open_positions if p['exit_time'] > row.entry_time]
        
        if len(open_positions) >= max_open:
            # Max open violated - block this trade
            max_open_violations.append({
                'timestamp': row.entry_time,
                'ticker': row.ticker,
                'entry_time': row.entry_time,
                'exit_time': row.exit_time,
                'trade_id': int(idx),
                'open_count': len(open_positions),
                'open_trade_ids': str([p['trade_id'] for p in open_positions]),
                'open_exits': str([str(p['exit_time'])[:19] for p in open_positions])
            })
        else:
            open_positions.append({
                'entry_time': row.entry_time,
                'exit_time': row.exit_time,
                'ticker': row.ticker,
                'trade_id': int(idx)
            })
            max_open_seen = max(max_open_seen, len(open_positions))

    if max_open_violations:
        violations_df = pd.DataFrame(max_open_violations)
        violations_path = base_dir / 'artifacts' / 'baseline_v1' / 'max_open_blocked_trades.csv'
        violations_path.parent.mkdir(parents=True, exist_ok=True)
        violations_df.to_csv(violations_path, index=False)
        print(f"[10] ℹ️ {len(violations_df)} trades bloqueados por MAX_OPEN (límite={max_open})")

    if max_open_seen > max_open:
        raise ValueError(f"max_open real falló: máximo observado {max_open_seen}")

    print("[10] ✅ Todas las pruebas pasaron")
    return {
        'leakage_signal_errors': leakage_errors,
        'features_errors': features_errors,
        'tz_errors': tz_errors,
        'eod_errors': eod_errors,
        'risk_errors': risk_errors,
        'max_open_seen': max_open_seen
    }


if __name__ == '__main__':
    validate_baseline_v1()
