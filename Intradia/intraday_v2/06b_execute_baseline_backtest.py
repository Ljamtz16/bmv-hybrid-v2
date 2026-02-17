# Script 06b — Execute Baseline v1 Backtest (15m, no windows)
#
# Inputs:
# - data/us/intraday_15m/consolidated_15m.parquet (o CSV)
# Outputs (artifacts/baseline_v1/):
# - trades.csv
# - equity_daily.csv
# - monthly_table.csv
# - summary_ticker_year_hour.csv

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
import json
import subprocess
import sys
from datetime import datetime

import importlib.util
import math
import joblib

CORE_TICKERS = {'SPY', 'QQQ', 'GS', 'JPM', 'CAT'}
PROBWIN_ALWAYS = {'NVDA', 'AMD'}
PROBWIN_VERSION = 'probwin_v1'


def _load_signals_builder(module_path: Path):
    spec = importlib.util.spec_from_file_location('baseline_signals', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_baseline_signals


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
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    return df


def _get_git_commit_hash(repo_path: Path) -> str | None:
    """Get current git commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _minute_of_day(ts: pd.Timestamp) -> int:
    return ts.hour * 60 + ts.minute


def _is_allowed_hour(ts: pd.Timestamp) -> bool:
    minutes = _minute_of_day(ts)
    morning = (minutes >= 9 * 60 + 30) and (minutes <= 11 * 60 + 30)
    afternoon = (minutes >= 15 * 60) and (minutes <= 16 * 60)
    return morning or afternoon


def _is_borderline_hour(ts: pd.Timestamp) -> bool:
    minutes = _minute_of_day(ts)
    morning_border = (minutes >= 10 * 60 + 30) and (minutes <= 11 * 60 + 30)
    afternoon_border = (minutes >= 15 * 60) and (minutes <= 16 * 60)
    return morning_border or afternoon_border


def _is_core_open(ts: pd.Timestamp) -> bool:
    minutes = _minute_of_day(ts)
    return (minutes >= 9 * 60 + 30) and (minutes <= 10 * 60 + 30)


def _evaluate_trade_per_share(
    bars_for_day: pd.DataFrame,
    entry_time: pd.Timestamp,
    entry_price: float,
    atr14: float
) -> dict | None:
    if atr14 <= 0:
        return None

    sl = entry_price - atr14
    tp = entry_price + 1.5 * atr14

    # Filtrar barras desde entry_time (inclusive)
    future = bars_for_day[bars_for_day['datetime'] >= entry_time]
    if future.empty:
        return None

    exit_time = None
    exit_price = None
    exit_reason = None

    for row in future.itertuples(index=False):
        high = row.high
        low = row.low

        hit_sl = low <= sl
        hit_tp = high >= tp

        if hit_sl and hit_tp:
            exit_reason = 'SL'
            exit_price = sl
            exit_time = row.datetime
            break
        if hit_sl:
            exit_reason = 'SL'
            exit_price = sl
            exit_time = row.datetime
            break
        if hit_tp:
            exit_reason = 'TP'
            exit_price = tp
            exit_time = row.datetime
            break

    if exit_reason is None:
        last_bar = bars_for_day.iloc[-1]
        exit_reason = 'EOD'
        exit_price = last_bar.close
        exit_time = last_bar.datetime

    pnl_per_share = exit_price - entry_price
    risk_per_share = atr14
    r_mult = pnl_per_share / risk_per_share if risk_per_share > 0 else 0.0

    return {
        'sl': sl,
        'tp': tp,
        'exit_time': exit_time,
        'exit_price': exit_price,
        'exit_reason': exit_reason,
        'pnl_per_share': pnl_per_share,
        'risk_per_share': risk_per_share,
        'r_mult': r_mult
    }


def execute_baseline_backtest(
    input_path: str | None = None,
    output_dir: str | None = None,
    timezone_target: str = 'America/New_York',
    equity_initial: float = 2000.0,
    risk_per_trade: float = 0.0075,
    max_open: int = 2,
    daily_stop_r: float = -2.0,
    use_probwin: bool = True,
    probwin_model_path: str | None = None,
    probwin_threshold: float = 0.55,
    universe: set[str] | None = None
) -> dict:
    base_dir = Path(__file__).resolve().parent
    data_path = Path(input_path) if input_path else _resolve_intraday_path(base_dir)

    signals_builder = _load_signals_builder(base_dir / '01b_build_baseline_signals.py')

    print(f"[06b] Leyendo datos desde {data_path}...")
    bars = _load_intraday(data_path)

    required = {'timestamp', 'open', 'high', 'low', 'close', 'volume', 'ticker'}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")

    bars = bars.rename(columns={'timestamp': 'datetime'})
    bars['datetime'] = pd.to_datetime(bars['datetime'])

    if bars['datetime'].dt.tz is None:
        bars['datetime'] = bars['datetime'].dt.tz_localize('UTC').dt.tz_convert(timezone_target)
    else:
        bars['datetime'] = bars['datetime'].dt.tz_convert(timezone_target)

    bars = bars.sort_values(['ticker', 'datetime']).reset_index(drop=True)
    bars['date_ny'] = bars['datetime'].dt.date

    # Features para ProbWin (en entry)
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

    # Generar señales baseline
    signals = signals_builder(
        input_path=str(data_path),
        output_parquet=None,
        output_csv=None,
        timezone_target=timezone_target
    )

    # Filtros: core tickers + horas permitidas
    use_universe = universe if universe is not None else CORE_TICKERS
    signals = signals[signals['ticker'].isin(use_universe)].copy()
    signals = signals[signals['entry_time'].apply(_is_allowed_hour)].copy()

    # Validaciones
    if signals['entry_time'].isna().any() or signals['entry_price'].isna().any() or signals['atr14'].isna().any():
        raise ValueError("NaNs críticos en señales filtradas")

    signals = signals.sort_values(['entry_time', 'ticker']).reset_index(drop=True)

    # Preindex bars por (ticker, date)
    bars_grouped = {k: g for k, g in bars.groupby(['ticker', 'date_ny'])}

    # Preindex features por (ticker, datetime)
    feature_cols = ['ret1_prev', 'ret4_prev', 'vol4', 'vol_z20', 'atr_ratio', 'body_pct']
    bar_features = bars[['ticker', 'datetime'] + feature_cols].copy()
    bar_features = bar_features.set_index(['ticker', 'datetime'])

    # ProbWin model
    probwin = None
    probwin_features = None
    if use_probwin:
        model_path = Path(probwin_model_path) if probwin_model_path else (base_dir / 'models' / 'probwin_v1.joblib')
        if model_path.exists():
            payload = joblib.load(model_path)
            probwin = payload.get('model')
            probwin_features = payload.get('feature_cols')
            print(f"[06b] ProbWin cargado: {model_path}")
        else:
            print(f"[06b] ⚠️ ProbWin no encontrado en {model_path}; gating desactivado")
            use_probwin = False

    # Simulación con control de max_open y daily stop
    equity = equity_initial
    open_positions = []
    trades = []
    daily_r = {}
    daily_pnl = {}

    def close_positions_up_to(ts: pd.Timestamp):
        nonlocal equity
        remaining = []
        for pos in open_positions:
            if pos['exit_time'] <= ts:
                equity += pos['pnl']
                d = pos['exit_time'].date()
                daily_r[d] = daily_r.get(d, 0.0) + pos['r_mult']
                daily_pnl[d] = daily_pnl.get(d, 0.0) + pos['pnl']
            else:
                remaining.append(pos)
        return remaining

    for row in signals.itertuples(index=False):
        entry_time = row.entry_time
        ticker = row.ticker
        entry_price = float(row.entry_price)
        atr14 = float(row.atr14)
        date_ny = row.date_ny
        hour_bucket = row.hour_bucket

        probwin_score = np.nan
        allowed = True
        block_reason = ''

        # Cerrar posiciones que ya salieron
        open_positions = close_positions_up_to(entry_time)

        equity_at_entry = equity
        risk_cash = equity_at_entry * risk_per_trade

        # Daily stop
        if daily_r.get(date_ny, 0.0) <= daily_stop_r:
            allowed = False
            block_reason = 'DAILY_STOP'

        # Max open
        if allowed and len(open_positions) >= max_open:
            allowed = False
            block_reason = 'MAX_OPEN'

        # ProbWin gating (selectivo)
        if allowed and use_probwin:
            gate_required = False
            if ticker in PROBWIN_ALWAYS:
                gate_required = True
            elif _is_borderline_hour(entry_time):
                gate_required = True
            elif (ticker in CORE_TICKERS) and _is_core_open(entry_time):
                gate_required = False

            if gate_required:
                try:
                    feat_row = bar_features.loc[(ticker, entry_time)]
                    if feat_row[feature_cols].isna().any():
                        allowed = False
                        block_reason = 'MISSING_FEATURES'
                    else:
                        feat = feat_row.to_dict()
                        feat['hour_bucket'] = entry_time.strftime('%H:%M')
                        feat['ticker'] = ticker

                        feat_df = pd.DataFrame([feat])
                        feat_df = pd.get_dummies(feat_df, columns=['ticker', 'hour_bucket'], prefix=['ticker', 'hour'])

                        for col in probwin_features:
                            if col not in feat_df.columns:
                                feat_df[col] = 0.0
                        feat_df = feat_df[probwin_features]
                        
                        # Fill any remaining NaNs with 0 before prediction
                        feat_df = feat_df.fillna(0.0)

                        probwin_score = float(probwin.predict_proba(feat_df)[:, 1][0])
                        if probwin_score < probwin_threshold:
                            allowed = False
                            block_reason = 'PROBWIN_LOW'
                except KeyError:
                    allowed = False
                    block_reason = 'MISSING_FEATURES'

        # Obtener barras del día
        key = (ticker, date_ny)
        if key not in bars_grouped:
            allowed = False
            if not block_reason:
                block_reason = 'NO_DATA'

        if allowed:
            eval_result = _evaluate_trade_per_share(
                bars_grouped[key],
                entry_time,
                entry_price,
                atr14
            )
            if not eval_result:
                allowed = False
                block_reason = 'NO_EVAL'

        if allowed:
            risk_per_share = eval_result['risk_per_share']
            if risk_per_share <= 0:
                allowed = False
                block_reason = 'BAD_RISK'

        shares = 0
        pnl = 0.0
        r_mult = 0.0
        exit_time = pd.NaT
        exit_price = np.nan
        exit_reason = 'BLOCKED'
        sl = np.nan
        tp = np.nan

        if allowed:
            shares = int(math.floor(risk_cash / risk_per_share))
            if shares <= 0:
                allowed = False
                block_reason = 'SIZE_ZERO'
            else:
                pnl = eval_result['pnl_per_share'] * shares
                r_mult = eval_result['r_mult']
                exit_time = eval_result['exit_time']
                exit_price = eval_result['exit_price']
                exit_reason = eval_result['exit_reason']
                sl = eval_result['sl']
                tp = eval_result['tp']

        trade = {
            'ticker': ticker,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry': entry_price,
            'sl': sl,
            'tp': tp,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'r_mult': r_mult,
            'shares': shares,
            'pnl': pnl,
            'hour_bucket': hour_bucket,
            'date_ny': date_ny,
            'equity_at_entry': equity_at_entry,
            'risk_cash': risk_cash,
            'probwin': probwin_score,
            'allowed': allowed,
            'block_reason': block_reason,
            'threshold': probwin_threshold if use_probwin else np.nan,
            'model_version': PROBWIN_VERSION if use_probwin else ''
        }
        trades.append(trade)

        if allowed:
            open_positions.append({
                'exit_time': eval_result['exit_time'],
                'pnl': pnl,
                'r_mult': r_mult
            })

    # Cerrar posiciones restantes al final
    if open_positions:
        last_time = bars['datetime'].max()
        open_positions = close_positions_up_to(last_time)

    trades_df = pd.DataFrame(trades)

    # Equity daily
    daily_rows = []
    equity_running = equity_initial
    running_max = equity_initial

    for d in sorted(daily_pnl.keys()):
        pnl_day = daily_pnl.get(d, 0.0)
        equity_start = equity_running
        equity_running = equity_running + pnl_day
        running_max = max(running_max, equity_running)
        dd = equity_running - running_max
        daily_rows.append({
            'date_ny': d,
            'equity_end': equity_running,
            'pnl_day': pnl_day,
            'dd': dd
        })

    equity_daily_df = pd.DataFrame(daily_rows)

    # Monthly table
    monthly_rows = []
    if not equity_daily_df.empty:
        equity_daily_df['month'] = pd.to_datetime(equity_daily_df['date_ny']).dt.to_period('M').astype(str)
        for month, g in equity_daily_df.groupby('month'):
            g = g.sort_values('date_ny')
            equity_start = (g['equity_end'].iloc[0] - g['pnl_day'].iloc[0]) if len(g) > 0 else equity_initial
            pnl = g['pnl_day'].sum()
            equity_end = g['equity_end'].iloc[-1]
            return_pct = (pnl / equity_start) * 100 if equity_start != 0 else 0.0
            monthly_rows.append({
                'month': month,
                'equity_start': equity_start,
                'pnl': pnl,
                'return_pct': return_pct,
                'equity_end': equity_end
            })

    monthly_df = pd.DataFrame(monthly_rows)

    # Summary por ticker/año/hour_bucket
    summary_df = pd.DataFrame()
    if not trades_df.empty:
        trades_df['year'] = pd.to_datetime(trades_df['entry_time']).dt.year
        trades_use = trades_df[trades_df.get('allowed', True) == True].copy()
        grouped = trades_use.groupby(['ticker', 'year', 'hour_bucket'])
        rows = []
        for (ticker, year, hour_bucket), g in grouped:
            wins = g[g['pnl'] > 0]['pnl'].sum()
            losses = g[g['pnl'] < 0]['pnl'].sum()
            pf = (wins / abs(losses)) if losses != 0 else float('inf')
            rows.append({
                'ticker': ticker,
                'year': year,
                'hour_bucket': hour_bucket,
                'trades': len(g),
                'win_rate': float((g['pnl'] > 0).mean() * 100),
                'avg_R': float(g['r_mult'].mean()),
                'PF': float(pf)
            })
        summary_df = pd.DataFrame(rows)

    # Guardar outputs
    output_dir_path = Path(output_dir) if output_dir else base_dir / 'artifacts' / 'baseline_v1'
    output_dir_path.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir_path / 'trades.csv'
    equity_path = output_dir_path / 'equity_daily.csv'
    monthly_path = output_dir_path / 'monthly_table.csv'
    summary_path = output_dir_path / 'summary_ticker_year_hour.csv'
    blocked_trades_path = output_dir_path / 'blocked_trades.csv'
    blocked_summary_path = output_dir_path / 'blocked_summary.json'
    metadata_path = output_dir_path / 'run_metadata.json'

    trades_df.to_csv(trades_path, index=False)
    equity_daily_df.to_csv(equity_path, index=False)
    monthly_df.to_csv(monthly_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    # Export blocked trades
    if not trades_df.empty:
        blocked_df = trades_df[trades_df.get('allowed', False) == False].copy()
        if not blocked_df.empty:
            # Select minimal columns
            blocked_cols = ['entry_time', 'ticker', 'hour_bucket', 'block_reason', 
                           'equity_at_entry', 'risk_cash', 'entry', 'sl', 'tp',
                           'probwin', 'threshold']
            blocked_export = blocked_df[[c for c in blocked_cols if c in blocked_df.columns]]
            blocked_export.to_csv(blocked_trades_path, index=False)
            print(f"[06b] ✅ Blocked trades guardados en: {blocked_trades_path}")
            
            # Export blocked summary
            blocked_summary = blocked_df['block_reason'].value_counts().to_dict()
            with open(blocked_summary_path, 'w') as f:
                json.dump(blocked_summary, f, indent=2)
            print(f"[06b] ✅ Blocked summary guardado en: {blocked_summary_path}")

    # Export run metadata
    git_commit = _get_git_commit_hash(base_dir.parent)
    metadata = {
        'run_timestamp': datetime.utcnow().isoformat() + 'Z',
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'repo_root': str(base_dir.parent),
        'data_path': str(data_path) if 'data_path' in locals() else None,
        'params': {
            'capital_initial': equity_initial,
            'risk_per_trade': risk_per_trade,
            'max_open': max_open,
            'daily_stop_R': daily_stop_r,
            'atr_window': 14,
            'sl_mult': 1.0,
            'tp_mult': 1.5,
            'tie_break_rule': 'first_signal'
        },
        'filters': {
            'core_tickers': list(CORE_TICKERS),
            'allowed_hours_ny': ['09:30-11:30', '15:00-16:00']
        },
        'counts': {
            'signals_generated': len(signals) if 'signals' in locals() else 0,
            'trades_allowed': int((trades_df.get('allowed', True) == True).sum()) if not trades_df.empty else 0,
            'trades_blocked': int((trades_df.get('allowed', False) == False).sum()) if not trades_df.empty else 0
        },
        'output_paths': {
            'trades': str(trades_path),
            'blocked_trades': str(blocked_trades_path),
            'equity_daily': str(equity_path),
            'monthly_table': str(monthly_path),
            'summary_ticker_year_hour': str(summary_path)
        },
        'git_commit': git_commit
    }
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"[06b] ✅ Metadata guardado en: {metadata_path}")

    print(f"[06b] ✅ Trades guardados en: {trades_path}")
    print(f"[06b] ✅ Equity daily guardado en: {equity_path}")
    print(f"[06b] ✅ Monthly table guardado en: {monthly_path}")
    print(f"[06b] ✅ Summary guardado en: {summary_path}")

    return {
        'trades': int(len(trades_df)),
        'equity_end': float(equity_running) if not equity_daily_df.empty else float(equity_initial),
        'dates': int(equity_daily_df['date_ny'].nunique()) if not equity_daily_df.empty else 0
    }


if __name__ == '__main__':
    execute_baseline_backtest()
