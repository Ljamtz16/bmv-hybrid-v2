# Script 01b — Build Baseline v1 Signals (15m, no windows)
# Genera señales breakout 4 velas con entrada en la siguiente vela
#
# Input:
# - data/us/intraday_15m/consolidated_15m.parquet (o CSV)
# Output:
# - artifacts/baseline_v1/baseline_signals.parquet
# - artifacts/baseline_v1/baseline_signals.csv

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path


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


def build_baseline_signals(
    input_path: str | None = None,
    output_parquet: str | None = None,
    output_csv: str | None = None,
    timezone_target: str = 'America/New_York'
) -> pd.DataFrame:
    base_dir = Path(__file__).resolve().parent
    data_path = Path(input_path) if input_path else _resolve_intraday_path(base_dir)

    print(f"[01b] Leyendo datos desde {data_path}...")
    df = _load_intraday(data_path)

    required = {'timestamp', 'open', 'high', 'low', 'close', 'volume', 'ticker'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")

    # Normalizar datetime
    df = df.rename(columns={'timestamp': 'datetime'})
    df['datetime'] = pd.to_datetime(df['datetime'])

    # Convertir TZ a NY
    if df['datetime'].dt.tz is None:
        df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(timezone_target)
    else:
        df['datetime'] = df['datetime'].dt.tz_convert(timezone_target)

    # Ordenar
    df = df.sort_values(['ticker', 'datetime']).reset_index(drop=True)

    # Calcular TR y ATR14 por ticker
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    tr = np.maximum.reduce([
        df['high'] - df['low'],
        (df['high'] - df['prev_close']).abs(),
        (df['low'] - df['prev_close']).abs()
    ])
    df['tr'] = pd.Series(tr, index=df.index).fillna(df['high'] - df['low'])
    df['atr14'] = (
        df.groupby('ticker')['tr']
        .transform(lambda x: x.rolling(14, min_periods=1).mean())
    )

    # Breakout: close[t] > max(high[t-4:t-1])
    rolling_high_4 = (
        df.groupby('ticker')['high']
        .transform(lambda x: x.shift(1).rolling(4, min_periods=4).max())
    )
    df['signal'] = df['close'] > rolling_high_4

    # Entry en la siguiente vela
    df['entry_time'] = df.groupby('ticker')['datetime'].shift(-1)
    df['entry_price'] = df.groupby('ticker')['open'].shift(-1)

    # ATR disponible al momento de entry: usar ATR del bar de señal (t)
    df['atr14_entry'] = df['atr14']

    # Filtrar señales válidas
    signals = df[df['signal']].copy()
    signals = signals.dropna(subset=['entry_time', 'entry_price', 'atr14_entry'])

    # Fecha NY y hour_bucket (de entry)
    signals['date_ny'] = signals['entry_time'].dt.date
    signals['hour_bucket'] = signals['entry_time'].dt.strftime('%H:%M')

    # Validaciones mínimas
    if signals['entry_time'].isna().any() or signals['entry_price'].isna().any():
        raise ValueError("Se encontraron NaNs críticos en entry_time o entry_price")

    # Output
    cols = [
        'ticker', 'datetime', 'entry_time', 'entry_price',
        'atr14_entry', 'date_ny', 'hour_bucket'
    ]
    signals_out = signals[cols].rename(columns={'datetime': 'signal_time', 'atr14_entry': 'atr14'})

    output_dir = None
    if output_parquet:
        output_dir = Path(output_parquet).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        signals_out.to_parquet(output_parquet, index=False)
        print(f"[01b] ✅ Guardado parquet en: {output_parquet}")

    if output_csv:
        output_dir = Path(output_csv).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        signals_out.to_csv(output_csv, index=False)
        print(f"[01b] ✅ Guardado CSV en: {output_csv}")

    print(f"[01b] Señales generadas: {len(signals_out):,}")
    return signals_out


if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / 'artifacts' / 'baseline_v1'
    output_parquet = str(output_dir / 'baseline_signals.parquet')
    output_csv = str(output_dir / 'baseline_signals.csv')

    build_baseline_signals(
        input_path=None,
        output_parquet=output_parquet,
        output_csv=output_csv
    )
