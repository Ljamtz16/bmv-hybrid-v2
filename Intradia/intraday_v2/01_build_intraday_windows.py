# Script 01 — Build Intraday Windows
# Crea ventanas intradía (OPEN/CLOSE) por (ticker, date, window)
#
# Input:  consolidated_15m.parquet (ticker, datetime/timestamp, open, high, low, close, volume)
# Output: artifacts/intraday_windows.parquet

import pandas as pd
import numpy as np
from pathlib import Path


def _parse_time_to_minutes(t: str) -> int:
    hh, mm = t.split(':')
    return int(hh) * 60 + int(mm)


def build_intraday_windows(
    input_path: str,
    output_path: str,
    regime_path: str | None = None,
    filter_operable_days: bool = True,
    timezone_target: str = 'America/New_York'
) -> pd.DataFrame:
    """
    Construye ventanas intradía OPEN/CLOSE desde velas 15m.

    Returns:
        DataFrame con columnas:
        ticker, date, window, w_open, w_high, w_low, w_close, w_volume,
        start_time, end_time, n_bars
    """
    print(f"[01] Leyendo datos desde {input_path}...")
    df = pd.read_parquet(input_path)

    print(f"[01] Filas cargadas: {len(df):,}")
    print(f"[01] Columnas disponibles: {df.columns.tolist()}")

    # Normalizar nombre de columna datetime/timestamp
    if 'timestamp' in df.columns and 'datetime' not in df.columns:
        df = df.rename(columns={'timestamp': 'datetime'})

    required_cols = ['ticker', 'datetime', 'open', 'high', 'low', 'close', 'volume']
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")

    # Convertir datetime
    df['datetime'] = pd.to_datetime(df['datetime'])

    # Timezone handling
    if df['datetime'].dt.tz is None:
        # Naive -> asumir horario mercado NY
        df['datetime'] = df['datetime'].dt.tz_localize(timezone_target)
    else:
        # Aware -> convertir a NY
        df['datetime'] = df['datetime'].dt.tz_convert(timezone_target)

    # Crear date después del timezone correcto
    df['date'] = df['datetime'].dt.floor('D')

    print(f"[01] Rango de fechas: {df['date'].min()} → {df['date'].max()}")
    print(f"[01] Tickers únicos: {df['ticker'].nunique()}")

    # Filtrar por régimen (opcional)
    if regime_path and Path(regime_path).exists() and filter_operable_days:
        print(f"[01] Filtrando por días operables desde: {regime_path}")
        regime = pd.read_parquet(regime_path)
        required_regime_cols = ['ticker', 'date', 'is_high_vol', 'is_wide_range', 'is_directional']
        missing_regime = set(required_regime_cols) - set(regime.columns)
        if missing_regime:
            raise ValueError(f"Regime table sin columnas: {missing_regime}")

        operable = regime[
            regime['is_high_vol'] & regime['is_wide_range'] & regime['is_directional']
        ][['ticker', 'date']]

        before = len(df)
        df = df.merge(operable, on=['ticker', 'date'], how='inner')
        after = len(df)
        print(f"[01] Filas después de filtrar operables: {after:,} (antes: {before:,})")

    # Definir ventanas intradía
    windows = [
        {'window': 'OPEN', 'start': '09:30', 'end': '10:30'},
        {'window': 'CLOSE', 'start': '14:00', 'end': '15:00'}
    ]

    # Precalcular minutos del día
    df['minute_of_day'] = df['datetime'].dt.hour * 60 + df['datetime'].dt.minute

    # Ordenar para first/last
    df = df.sort_values(['ticker', 'date', 'datetime'])

    results = []
    for w in windows:
        start_min = _parse_time_to_minutes(w['start'])
        end_min = _parse_time_to_minutes(w['end'])

        mask = (df['minute_of_day'] >= start_min) & (df['minute_of_day'] <= end_min)
        dfw = df[mask]

        agg = dfw.groupby(['ticker', 'date'], as_index=False).agg(
            w_open=('open', 'first'),
            w_high=('high', 'max'),
            w_low=('low', 'min'),
            w_close=('close', 'last'),
            w_volume=('volume', 'sum'),
            n_bars=('close', 'count')
        )

        agg['window'] = w['window']
        agg['start_time'] = w['start']
        agg['end_time'] = w['end']

        results.append(agg)

    intraday_windows = pd.concat(results, ignore_index=True)

    # Validaciones
    print(f"\n[01] === VALIDACIONES ===")
    duplicates = intraday_windows.duplicated(subset=['ticker', 'date', 'window']).sum()
    print(f"[01] Duplicados (ticker, date, window): {duplicates}")
    if duplicates > 0:
        raise ValueError(f"Se encontraron {duplicates} duplicados en (ticker, date, window)")

    # Distribución por ventana
    window_dist = intraday_windows['window'].value_counts()
    print(f"[01] Distribución de ventanas:\n{window_dist}")

    # n_bars stats
    n_bars_stats = intraday_windows['n_bars'].describe(percentiles=[0.1, 0.5, 0.9])
    print(f"[01] Estadísticas n_bars:\n{n_bars_stats}")

    # Ventanas vacías
    zero_bars = (intraday_windows['n_bars'] == 0).sum()
    print(f"[01] Ventanas con n_bars=0: {zero_bars}")

    # Guardar
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    intraday_windows.to_parquet(output_path, index=False)
    print(f"\n[01] ✅ Guardado en: {output_path}")
    print(f"[01] Filas generadas: {len(intraday_windows):,}")

    return intraday_windows


if __name__ == '__main__':
    INPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet'
    OUTPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_windows.parquet'
    REGIME_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\regime_table.parquet'

    intraday_windows = build_intraday_windows(
        INPUT_FILE,
        OUTPUT_FILE,
        regime_path=REGIME_FILE,
        filter_operable_days=False
    )

    print(f"\n[01] === MUESTRA ===")
    print(intraday_windows.head(10))