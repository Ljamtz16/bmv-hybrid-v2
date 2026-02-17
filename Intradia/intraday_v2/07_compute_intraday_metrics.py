# Script 07 — Compute Intraday Metrics
# Calcula métricas agregadas y por segmento del backtest intradía
#
# Inputs:
# - artifacts/intraday_trades.csv
# - artifacts/intraday_equity_curve.csv (opcional)
# - artifacts/intraday_plan_clean.csv (para buckets de prob_win)
#
# Outputs:
# - artifacts/intraday_metrics.json
# - artifacts/intraday_weekly.csv

import pandas as pd
import numpy as np
import json
from pathlib import Path


def _compute_pf(pnl_wins: float, pnl_losses: float) -> float:
	return pnl_wins / abs(pnl_losses) if pnl_losses != 0 else float('inf')


def compute_intraday_metrics(
	trades_path: str,
	equity_path: str,
	plan_path: str,
	metrics_path: str,
	weekly_path: str
) -> dict:
	print(f"[07] Cargando trades desde {trades_path}...")
	trades = pd.read_csv(trades_path)

	print(f"[07] Cargando plan desde {plan_path}...")
	plan = pd.read_csv(plan_path)

	# Parse times (normalizar TZ para evitar mezclas)
	trades['entry_time'] = pd.to_datetime(trades['entry_time'], utc=True).dt.tz_convert('America/New_York')
	plan['entry_time'] = pd.to_datetime(plan['entry_time'], utc=True).dt.tz_convert('America/New_York')

	# Merge para traer prob_win y window
	plan_cols = ['ticker', 'entry_time', 'window', 'prob_win_intraday', 'side']
	plan_use = plan[plan_cols].copy()

	trades = trades.merge(plan_use, on=['ticker', 'entry_time', 'side'], how='left')

	# Valid trades (TP/SL)
	valid = trades[trades['exit_reason'].isin(['TP', 'SL'])].copy()
	print(f"[07] Trades válidos (TP/SL): {len(valid):,} / {len(trades):,}")

	# PnL totals
	pnl_total = valid['pnl'].sum()
	pnl_wins = valid[valid['pnl'] > 0]['pnl'].sum()
	pnl_losses = valid[valid['pnl'] < 0]['pnl'].sum()

	pf = _compute_pf(pnl_wins, pnl_losses)
	wr = (valid['pnl'] > 0).mean() * 100 if len(valid) > 0 else 0

	# Equity curve / Max DD
	valid = valid.sort_values('entry_time')
	valid['cum_pnl'] = valid['pnl'].cumsum()
	running_max = valid['cum_pnl'].cummax()
	dd = valid['cum_pnl'] - running_max
	max_dd = dd.min() if len(dd) > 0 else 0

	# R-multiple (si hay sl_price)
	if 'sl_price' in valid.columns:
		risk = (valid['entry_price'] - valid['sl_price']).abs()
		valid['r_multiple'] = valid['pnl'] / risk.replace(0, np.nan)
	else:
		valid['r_multiple'] = np.nan

	# Por ticker / window / side
	def _group_metrics(df, group_col):
		out = []
		for key, g in df.groupby(group_col):
			g_pnl = g['pnl'].sum()
			g_wins = g[g['pnl'] > 0]['pnl'].sum()
			g_losses = g[g['pnl'] < 0]['pnl'].sum()
			out.append({
				group_col: key,
				'trades': len(g),
				'wr': float((g['pnl'] > 0).mean() * 100),
				'pnl_total': float(g_pnl),
				'pf': float(_compute_pf(g_wins, g_losses))
			})
		return out

	metrics_by_ticker = _group_metrics(valid, 'ticker')
	metrics_by_window = _group_metrics(valid, 'window') if 'window' in valid.columns else []
	metrics_by_side = _group_metrics(valid, 'side')

	# Buckets por prob_win_intraday
	buckets = [0.60, 0.65, 0.70, 0.80, 1.01]
	valid['prob_bucket'] = pd.cut(valid['prob_win_intraday'], bins=buckets, right=False)
	metrics_by_bucket = []
	for bucket, g in valid.groupby('prob_bucket', observed=True):
		g_pnl = g['pnl'].sum()
		g_wins = g[g['pnl'] > 0]['pnl'].sum()
		g_losses = g[g['pnl'] < 0]['pnl'].sum()
		metrics_by_bucket.append({
			'prob_bucket': str(bucket),
			'trades': len(g),
			'wr': float((g['pnl'] > 0).mean() * 100),
			'pnl_total': float(g_pnl),
			'pf': float(_compute_pf(g_wins, g_losses))
		})

	# Weekly summary
	# Semana basada en NY time (naive)
	valid['entry_time_naive'] = valid['entry_time'].dt.tz_localize(None)
	valid['week'] = valid['entry_time_naive'].dt.to_period('W').dt.start_time
	weekly = valid.groupby('week').agg(
		trades=('pnl', 'count'),
		pnl_total=('pnl', 'sum'),
		wr=('pnl', lambda s: (s > 0).mean() * 100),
		avg_pnl=('pnl', 'mean')
	).reset_index()

	# Save weekly
	weekly_path = Path(weekly_path)
	weekly_path.parent.mkdir(parents=True, exist_ok=True)
	weekly.to_csv(weekly_path, index=False)
	print(f"[07] ✅ Weekly summary guardado en: {weekly_path}")

	# Metrics JSON
	metrics = {
		'total_trades': int(len(trades)),
		'valid_trades': int(len(valid)),
		'pnl_total': float(pnl_total),
		'pnl_wins': float(pnl_wins),
		'pnl_losses': float(pnl_losses),
		'pf': float(pf),
		'wr': float(wr),
		'max_dd': float(max_dd),
		'avg_pnl': float(valid['pnl'].mean()) if len(valid) > 0 else 0,
		'avg_r_multiple': float(valid['r_multiple'].mean()) if len(valid) > 0 else 0,
		'metrics_by_ticker': metrics_by_ticker,
		'metrics_by_window': metrics_by_window,
		'metrics_by_side': metrics_by_side,
		'metrics_by_prob_bucket': metrics_by_bucket
	}

	metrics_path = Path(metrics_path)
	metrics_path.parent.mkdir(parents=True, exist_ok=True)
	with open(metrics_path, 'w') as f:
		json.dump(metrics, f, indent=2)
	print(f"[07] ✅ Metrics guardadas en: {metrics_path}")

	# Resumen rápido
	print(f"\n[07] === RESUMEN ===")
	print(f"[07] PF: {pf:.2f} | WR: {wr:.1f}% | PnL: ${pnl_total:.2f} | Max DD: ${max_dd:.2f}")
	print(f"[07] Buckets prob_win: {metrics_by_bucket}")

	return metrics


if __name__ == '__main__':
	TRADES_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
	EQUITY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_equity_curve.csv'
	PLAN_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan_clean.csv'
	METRICS_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_metrics.json'
	WEEKLY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_weekly.csv'
    
	compute_intraday_metrics(
		TRADES_FILE,
		EQUITY_FILE,
		PLAN_FILE,
		METRICS_FILE,
		WEEKLY_FILE
	)