# Script 03 — Build Intraday ML Dataset
# Construye dataset supervisado por (ticker, date, window)
#
# Inputs:
# - artifacts/intraday_windows.parquet
# - artifacts/regime_table.parquet
# - consolidated_15m.parquet (para labeling)
#
# Output:
# - artifacts/intraday_ml_dataset.parquet

import pandas as pd
import numpy as np
from pathlib import Path


def _parse_time_to_minutes(t: str) -> int:
	hh, mm = t.split(':')
	return int(hh) * 60 + int(mm)


def _combine_date_time(date_ts: pd.Timestamp, time_str: str) -> pd.Timestamp:
	minutes = _parse_time_to_minutes(time_str)
	return date_ts + pd.Timedelta(minutes=minutes)


def build_intraday_dataset(
	windows_path: str,
	regime_path: str,
	intraday_path: str,
	output_path: str,
	timezone_target: str = 'America/New_York',
	tp_mult: float = 0.8,
	sl_mult: float = 0.6,
	time_stop_bars: int = 16,
	drop_timeouts: bool = True
) -> pd.DataFrame:
	print(f"[03] Cargando ventanas desde {windows_path}...")
	windows = pd.read_parquet(windows_path)

	print(f"[03] Cargando régimen desde {regime_path}...")
	regime = pd.read_parquet(regime_path)

	print(f"[03] Cargando intradía 15m desde {intraday_path}...")
	bars = pd.read_parquet(intraday_path)

	# Normalizar datetime en intradía
	if 'timestamp' in bars.columns and 'datetime' not in bars.columns:
		bars = bars.rename(columns={'timestamp': 'datetime'})

	bars['datetime'] = pd.to_datetime(bars['datetime'])

	if bars['datetime'].dt.tz is None:
		bars['datetime'] = bars['datetime'].dt.tz_localize(timezone_target)
	else:
		bars['datetime'] = bars['datetime'].dt.tz_convert(timezone_target)

	# Date key sin TZ para joins robustos
	windows['date_key'] = pd.to_datetime(windows['date']).dt.date
	regime['date_key'] = pd.to_datetime(regime['date']).dt.date
	bars['date_key'] = bars['datetime'].dt.date

	# Preparar prev_close para features adicionales
	regime = regime.sort_values(['ticker', 'date'])
	if 'close' in regime.columns:
		regime['close_prev'] = regime.groupby('ticker')['close'].shift(1)

	# Usar columnas previas para anti-leakage
	regime_features = [
		'ticker', 'date_key',
		'atr14_prev', 'ema20_prev', 'daily_range_pct_prev',
		'is_high_vol_prev', 'is_wide_range_prev', 'is_directional_prev',
		'side_prev',
		'close_prev'
	]

	missing_regime = set(regime_features) - set(regime.columns)
	if missing_regime:
		raise ValueError(
			f"Faltan columnas previas en régimen: {missing_regime}. "
			f"Re-ejecuta 02_build_regime_table.py"
		)

	regime_use = regime[regime_features].copy()

	# Join windows + regime (prev)
	df = windows.merge(
		regime_use,
		on=['ticker', 'date_key'],
		how='left'
	)

	# Drop rows sin features previas
	before = len(df)
	df = df.dropna(subset=['atr14_prev', 'ema20_prev', 'side_prev'])
	after = len(df)
	print(f"[03] Filas después de drop de prev features: {after:,} (antes: {before:,})")

	# Renombrar para claridad
	df = df.rename(columns={
		'atr14_prev': 'atr14',
		'ema20_prev': 'ema20',
		'daily_range_pct_prev': 'daily_range_pct',
		'is_high_vol_prev': 'is_high_vol',
		'is_wide_range_prev': 'is_wide_range',
		'is_directional_prev': 'is_directional',
		'side_prev': 'side',
		'close_prev': 'prev_close'
	})

	# BUY-only
	before_side = len(df)
	df = df[df['side'] == 'BUY'].copy()
	print(f"[03] Filas después de filtrar BUY: {len(df):,} (antes: {before_side:,})")

	# === Features de ventana ===
	df['window_range'] = (df['w_high'] - df['w_low']) / df['w_open']
	df['window_return'] = (df['w_close'] - df['w_open']) / df['w_open']
	df['window_body'] = (df['w_close'] - df['w_open']).abs() / df['w_open']

	# === Features combinadas ===
	df['w_close_vs_ema'] = (df['w_close'] - df['ema20']) / df['ema20']
	df['range_to_atr'] = (df['w_high'] - df['w_low']) / df['atr14']
	df['body_to_atr'] = (df['w_close'] - df['w_open']).abs() / df['atr14']

	# === Features adicionales ===
	df['gap_atr'] = (df['w_open'] - df['prev_close']) / df['atr14']
	df['overnight_ret'] = (df['w_open'] - df['prev_close']) / df['prev_close']

	# Relative volume (rolling 20d por ticker+window)
	windows_sorted = windows.sort_values(['ticker', 'window', 'date'])
	windows_sorted['w_volume_roll20'] = (
		windows_sorted
		.groupby(['ticker', 'window'])['w_volume']
		.transform(lambda s: s.rolling(20, min_periods=1).mean().shift(1))
	)
	roll_vol = windows_sorted[['ticker', 'date_key', 'window', 'w_volume_roll20']]
	df = df.merge(roll_vol, on=['ticker', 'date_key', 'window'], how='left')
	df['rvol'] = df['w_volume'] / df['w_volume_roll20']

	# Interaction features
	df['body_to_atr_x_high_vol'] = df['body_to_atr'] * df['is_high_vol']
	df['range_to_atr_x_directional'] = df['range_to_atr'] * df['is_directional']

	# === Labeling ===
	# Preindex bars por (ticker, date_key) para búsqueda rápida
	bars = bars.sort_values(['ticker', 'datetime'])
	bars_grouped = {k: g for k, g in bars.groupby(['ticker', 'date_key'])}

	labels = []
	outcomes = []
	vwap_dists = []

	print(f"[03] Generando labels (tp={tp_mult}, sl={sl_mult}, time_stop={time_stop_bars} bars)...")
	for row in df.itertuples(index=False):
		ticker = row.ticker
		date_key = row.date_key
		window = row.window
		side = row.side

		entry_price = row.w_open
		entry_time = _combine_date_time(pd.Timestamp(row.date), row.start_time)
		end_time = _combine_date_time(pd.Timestamp(row.date), row.end_time)

		# Obtener barras del día
		key = (ticker, date_key)
		if key not in bars_grouped:
			labels.append(np.nan)
			outcomes.append('NO_DATA')
			vwap_dists.append(np.nan)
			continue

		day_bars = bars_grouped[key]

		# VWAP dentro de la ventana (no leakage)
		window_bars = day_bars[(day_bars['datetime'] >= entry_time) & (day_bars['datetime'] <= end_time)]
		if window_bars.empty or window_bars['volume'].sum() == 0:
			vwap_dists.append(np.nan)
		else:
			vwap = (window_bars['close'] * window_bars['volume']).sum() / window_bars['volume'].sum()
			vwap_dists.append((row.w_close - vwap) / vwap)

		# Filtrar barras posteriores a la entrada
		future = day_bars[day_bars['datetime'] > entry_time].head(time_stop_bars)
		if future.empty:
			labels.append(np.nan)
			outcomes.append('TIMEOUT')
			continue

		# Definir TP/SL (BUY only)
		tp = entry_price + tp_mult * row.atr14
		sl = entry_price - sl_mult * row.atr14

		hit = None
		for b in future.itertuples(index=False):
			high = b.high
			low = b.low

			hit_tp = high >= tp
			hit_sl = low <= sl

			# Si toca ambos, contar como SL (conservador)
			if hit_sl and hit_tp:
				hit = 0
				break
			if hit_tp:
				hit = 1
				break
			if hit_sl:
				hit = 0
				break

		if hit is None:
			labels.append(np.nan)
			outcomes.append('TIMEOUT')
		else:
			labels.append(hit)
			outcomes.append('TP' if hit == 1 else 'SL')

	df['y'] = labels
	df['outcome'] = outcomes
	df['vwap_dist'] = vwap_dists

	if drop_timeouts:
		before = len(df)
		df = df.dropna(subset=['y'])
		after = len(df)
		print(f"[03] Filas después de eliminar TIMEOUT: {after:,} (antes: {before:,})")

	# === Validaciones ===
	print(f"\n[03] === VALIDACIONES ===")
	print(f"[03] Filas dataset: {len(df):,}")
	print(f"[03] Distribución de window:\n{df['window'].value_counts()}")
	print(f"[03] Balance y:\n{df['y'].value_counts(normalize=True) * 100}")

	# WR por window
	wr_by_window = df.groupby('window')['y'].mean() * 100
	print(f"[03] WR por window:\n{wr_by_window}")

	# Guardar
	output_dir = Path(output_path).parent
	output_dir.mkdir(parents=True, exist_ok=True)
	df.to_parquet(output_path, index=False)
	print(f"\n[03] ✅ Guardado en: {output_path}")

	return df


if __name__ == '__main__':
    WINDOWS_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_windows.parquet'
    REGIME_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\regime_table.parquet'
    INTRADAY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet'
    OUTPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_ml_dataset.parquet'

    dataset = build_intraday_dataset(
        WINDOWS_FILE,
        REGIME_FILE,
        INTRADAY_FILE,
        OUTPUT_FILE,
        tp_mult=0.8,
        sl_mult=0.6,
        time_stop_bars=16,
        drop_timeouts=True
    )

    print(f"\n[03] === MUESTRA ===")
    print(dataset.head(10))