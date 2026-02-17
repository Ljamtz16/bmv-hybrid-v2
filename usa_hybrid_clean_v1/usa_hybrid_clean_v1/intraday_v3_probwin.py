#!/usr/bin/env python3
"""
Intraday V3 (desde cero) basado en prob_win como filtro principal.

Características:
- Entrada por ventanas horarias (UTC)
- Señal principal: prob_win (BUY si >= threshold, SELL si <= 1-threshold)
- SL/TP adaptativo basado en ATR diario
- 1 trade por ticker/día (primer ventana disponible)
"""

import argparse
import json
from pathlib import Path
from datetime import time

import numpy as np
import pandas as pd


def build_time_windows(num_windows: int):
    # Ventanas en UTC
    # 9:30-10:30 ET = 14:30-15:30 UTC
    # 11:00-12:00 ET = 16:00-17:00 UTC
    # 12:00-13:00 ET = 17:00-18:00 UTC
    # 13:00-14:00 ET = 18:00-19:00 UTC
    # 14:00-15:00 ET = 19:00-20:00 UTC
    all_windows = [
        (time(14, 30), time(15, 30)),
        (time(16, 0), time(17, 0)),
        (time(17, 0), time(18, 0)),
        (time(18, 0), time(19, 0)),
        (time(19, 0), time(20, 0)),
    ]

    if num_windows >= 5:
        return all_windows
    if num_windows == 4:
        return [all_windows[0], all_windows[1], all_windows[2], all_windows[4]]
    if num_windows == 3:
        return [all_windows[0], all_windows[2], all_windows[4]]
    return [all_windows[0], all_windows[4]]


def compute_daily_features(df_intraday: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    daily = df_intraday.groupby(['ticker', 'date']).agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
    ).reset_index()

    daily = daily.sort_values(['ticker', 'date'])

    out = []
    for ticker, df_t in daily.groupby('ticker'):
        df_t = df_t.copy()
        df_t['prev_close'] = df_t['close'].shift(1)
        df_t['tr'] = np.maximum.reduce([
            (df_t['high'] - df_t['low']).values,
            np.abs(df_t['high'] - df_t['prev_close']).fillna(0).values,
            np.abs(df_t['low'] - df_t['prev_close']).fillna(0).values,
        ])
        df_t['atr'] = df_t['tr'].rolling(window=period, min_periods=period).mean()
        df_t['ema20'] = df_t['close'].ewm(span=20, adjust=False).mean()
        df_t['daily_range_pct'] = (df_t['high'] - df_t['low']) / df_t['open']
        out.append(df_t[['ticker', 'date', 'open', 'close', 'atr', 'ema20', 'daily_range_pct']])

    return pd.concat(out, ignore_index=True)


def simulate_trades(
    df_intraday: pd.DataFrame,
    forecast: pd.DataFrame,
    daily_features: pd.DataFrame,
    capital: float,
    position_pct: float,
    prob_win_threshold: float,
    tp_multiplier: float,
    sl_multiplier: float,
    num_windows: int,
    max_trades_per_window: int,
    use_regime_filters: bool,
    atr_percentile: float,
    min_range_pct: float,
    directional_filter: bool,
):
    windows = build_time_windows(num_windows)

    # Merge daily features
    forecast = forecast.merge(daily_features, on=['ticker', 'date'], how='left')
    forecast = forecast.dropna(subset=['atr', 'ema20', 'daily_range_pct'])

    # Señal prob_win
    buy_mask = forecast['prob_win'] >= prob_win_threshold
    sell_mask = forecast['prob_win'] <= (1 - prob_win_threshold)
    forecast = forecast[buy_mask | sell_mask].copy()

    forecast['side'] = np.where(forecast['prob_win'] >= prob_win_threshold, 'BUY', 'SELL')

    # Regime filters (optional)
    if use_regime_filters:
        atr_p = forecast.groupby('ticker')['atr'].quantile(atr_percentile).to_dict()
        forecast['atr_threshold'] = forecast['ticker'].map(atr_p)
        forecast['is_high_vol'] = forecast['atr'] > forecast['atr_threshold']
        forecast['is_wide_range'] = forecast['daily_range_pct'] >= min_range_pct

        if directional_filter:
            forecast['is_directional'] = (
                ((forecast['open'] > forecast['ema20']) & (forecast['side'] == 'BUY')) |
                ((forecast['open'] < forecast['ema20']) & (forecast['side'] == 'SELL'))
            )
        else:
            forecast['is_directional'] = True

        forecast = forecast[
            (forecast['is_high_vol'] | forecast['is_wide_range']) &
            (forecast['is_directional'] == True)
        ].copy()

    # Agrupar intraday por ticker/date
    prices_by_ticker_date = {
        k: g.sort_values('datetime')
        for k, g in df_intraday.groupby(['ticker', 'date'])
    }

    trades = []
    trades_per_window = {}

    debug_no_data = 0
    debug_qty_zero = 0
    debug_no_window = 0

    for _, row in forecast.iterrows():
        ticker = row['ticker']
        date = row['date']
        side = row['side']
        atr = row['atr']

        key = (ticker, date)
        if key not in prices_by_ticker_date:
            debug_no_data += 1
            continue

        df_day = prices_by_ticker_date[key]

        # Seleccionar primer ventana disponible
        for w_idx, (start_t, end_t) in enumerate(windows):
            w_key = (ticker, date, w_idx)
            if trades_per_window.get(w_key, 0) >= max_trades_per_window:
                continue

            df_window = df_day[(df_day['datetime'].dt.time >= start_t) & (df_day['datetime'].dt.time <= end_t)]
            if df_window.empty:
                debug_no_window += 1
                continue

            entry_candle = df_window.iloc[0]
            entry_price = entry_candle['open']
            entry_time = entry_candle['datetime']

            qty = int((capital * position_pct) / entry_price)
            if qty == 0:
                debug_qty_zero += 1
                continue

            tp_distance = tp_multiplier * atr
            sl_distance = sl_multiplier * atr

            if side == 'BUY':
                tp_price = entry_price + tp_distance
                sl_price = entry_price - sl_distance
            else:
                tp_price = entry_price - tp_distance
                sl_price = entry_price + sl_distance

            # Simular desde entry_time hasta fin del día
            df_after = df_day[df_day['datetime'] >= entry_time]
            exit_reason = 'TIMEOUT'
            exit_price = df_after.iloc[-1]['close']
            exit_time = df_after.iloc[-1]['datetime']

            for _, candle in df_after.iterrows():
                high = candle['high']
                low = candle['low']

                if side == 'BUY' and high >= tp_price:
                    exit_reason = 'TP'
                    exit_price = tp_price
                    exit_time = candle['datetime']
                    break
                if side == 'SELL' and low <= tp_price:
                    exit_reason = 'TP'
                    exit_price = tp_price
                    exit_time = candle['datetime']
                    break
                if side == 'BUY' and low <= sl_price:
                    exit_reason = 'SL'
                    exit_price = sl_price
                    exit_time = candle['datetime']
                    break
                if side == 'SELL' and high >= sl_price:
                    exit_reason = 'SL'
                    exit_price = sl_price
                    exit_time = candle['datetime']
                    break

            pnl = (exit_price - entry_price) * qty if side == 'BUY' else (entry_price - exit_price) * qty
            capital += pnl

            trades.append({
                'ticker': ticker,
                'date': date,
                'side': side,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'entry_time': entry_time,
                'exit_time': exit_time,
                'exit_reason': exit_reason,
                'qty': qty,
                'pnl': pnl,
                'capital': capital,
                'prob_win': row['prob_win'],
                'atr': atr,
                'tp_distance': tp_distance,
                'sl_distance': sl_distance,
                'window': f"{start_t}-{end_t}",
            })

            trades_per_window[w_key] = trades_per_window.get(w_key, 0) + 1
            break

    debug = {
        'no_intraday_data': debug_no_data,
        'qty_zero': debug_qty_zero,
        'no_window_data': debug_no_window,
    }

    return trades, debug


def main():
    parser = argparse.ArgumentParser(description='Intraday V3 (prob_win)')
    parser.add_argument('--capital', type=float, required=True)
    parser.add_argument('--intraday', type=str, required=True)
    parser.add_argument('--forecast', type=str, default='data/daily/forecast_prob_win.parquet')
    parser.add_argument('--output-dir', type=str, required=True)
    parser.add_argument('--start-date', type=str, default='2022-02-01')
    parser.add_argument('--end-date', type=str, default='2025-12-31')
    parser.add_argument('--prob-win-threshold', type=float, default=0.55)
    parser.add_argument('--tp-multiplier', type=float, default=1.5)
    parser.add_argument('--sl-multiplier', type=float, default=0.75)
    parser.add_argument('--position-pct', type=float, default=0.25)
    parser.add_argument('--num-windows', type=int, default=3)
    parser.add_argument('--max-trades-per-window', type=int, default=5)
    parser.add_argument('--use-regime-filters', action='store_true')
    parser.add_argument('--atr-percentile', type=float, default=0.75)
    parser.add_argument('--min-range-pct', type=float, default=0.012)
    parser.add_argument('--directional-filter', action='store_true')
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("INTRADAY V3 - PROB_WIN PRIMARY")
    print("=" * 70)
    print(f"Capital: ${args.capital:,.2f}")
    print(f"Prob Win Threshold: {args.prob_win_threshold:.2f}")
    print(f"TP/SL: {args.tp_multiplier}x / {args.sl_multiplier}x ATR")
    print(f"Position: {args.position_pct*100:.0f}%")
    print(f"Windows: {args.num_windows}")
    print(f"Max trades/window: {args.max_trades_per_window}")
    print(f"Regime filters: {'ON' if args.use_regime_filters else 'OFF'}")
    if args.use_regime_filters:
        print(f"ATR percentile: {args.atr_percentile:.2f} | Min range: {args.min_range_pct:.3f} | Directional: {'ON' if args.directional_filter else 'OFF'}")
    print(f"Period: {args.start_date} -> {args.end_date}")
    print("=" * 70 + "\n")

    df_intraday = pd.read_parquet(args.intraday)
    if 'timestamp' in df_intraday.columns:
        df_intraday = df_intraday.rename(columns={'timestamp': 'datetime'})
    df_intraday['datetime'] = pd.to_datetime(df_intraday['datetime'])
    df_intraday['date'] = df_intraday['datetime'].dt.date

    forecast = pd.read_parquet(args.forecast)
    forecast['date'] = pd.to_datetime(forecast['date']).dt.date

    start_dt = pd.to_datetime(args.start_date).date()
    end_dt = pd.to_datetime(args.end_date).date()
    forecast = forecast[(forecast['date'] >= start_dt) & (forecast['date'] <= end_dt)].copy()

    print(f"[INFO] Intraday candles: {len(df_intraday):,}")
    print(f"[INFO] Forecast signals: {len(forecast):,}")

    print("[INFO] Calculando features diarios...")
    daily_features = compute_daily_features(df_intraday, period=14)

    print("[INFO] Simulando trades...")
    trades, debug = simulate_trades(
        df_intraday,
        forecast,
        daily_features,
        args.capital,
        args.position_pct,
        args.prob_win_threshold,
        args.tp_multiplier,
        args.sl_multiplier,
        args.num_windows,
        args.max_trades_per_window,
        args.use_regime_filters,
        args.atr_percentile,
        args.min_range_pct,
        args.directional_filter,
    )

    if not trades:
        print("[ERROR] No se generaron trades.")
        print(f"[DEBUG] {debug}")
        return

    df_trades = pd.DataFrame(trades)

    total_pnl = df_trades['pnl'].sum()
    final_capital = args.capital + total_pnl
    roi = (total_pnl / args.capital) * 100

    wins = df_trades[df_trades['pnl'] > 0]
    losses = df_trades[df_trades['pnl'] < 0]

    win_rate = len(wins) / len(df_trades) * 100 if len(df_trades) > 0 else 0
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0

    gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    exit_breakdown = df_trades['exit_reason'].value_counts().to_dict()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df_trades.to_csv(output_dir / 'all_trades.csv', index=False)

    summary = {
        'config': {
            'capital': args.capital,
            'prob_win_threshold': args.prob_win_threshold,
            'tp_multiplier': args.tp_multiplier,
            'sl_multiplier': args.sl_multiplier,
            'position_pct': args.position_pct,
            'num_windows': args.num_windows,
            'max_trades_per_window': args.max_trades_per_window,
            'start_date': args.start_date,
            'end_date': args.end_date,
        },
        'results': {
            'total_trades': len(df_trades),
            'total_pnl': round(total_pnl, 2),
            'final_capital': round(final_capital, 2),
            'roi_pct': round(roi, 2),
            'win_rate_pct': round(win_rate, 2),
            'wins': len(wins),
            'losses': len(losses),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'exit_breakdown': exit_breakdown,
            'debug': debug,
        },
    }

    with open(output_dir / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)
    print(f"Trades: {len(df_trades)}")
    print(f"P&L: ${total_pnl:,.2f}")
    print(f"ROI: {roi:+.2f}%")
    print(f"PF: {profit_factor:.2f}x")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Exit Breakdown: {exit_breakdown}")
    print("=" * 70)


if __name__ == '__main__':
    main()
