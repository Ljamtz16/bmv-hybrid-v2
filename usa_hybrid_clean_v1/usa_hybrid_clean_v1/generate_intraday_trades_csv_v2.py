#!/usr/bin/env python3
"""
Generador de trades intraday con filtros estrictos (v2)

Implementa checklist de robustez:
1. Time gating estricto (2 ventanas, máx 3 trades/ventana)
2. Filtro de régimen (ATR, rango, direccionalidad)
3. Patrones raros (prob_win > 0.60)
4. SL/TP adaptativo (basado en ATR)
5. Objetivo PF ≥ 1.15
"""

import argparse
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import time, datetime, timedelta


def calculate_regime_filters(df_intraday, forecast):
    """
    Calcula filtros de régimen por ticker-fecha (optimizado).
    
    Retorna DataFrame con:
    - ticker, date
    - atr: Average True Range (14 días)
    - daily_range_pct: (high - low) / open del día actual
    - ema20: EMA de 20 días
    - open_price: precio de apertura del día
    - is_high_vol: ATR > percentil 75
    - is_wide_range: rango diario > 1.5%
    - is_directional: precio > EMA20 (para BUY) o precio < EMA20 (para SELL)
    
    NOTA: Espera que df_intraday ya tenga columna 'date'
    """
    print("[INFO] Calculando régimen (optimizado)...")
    
    # Calcular daily OHLC
    daily = df_intraday.groupby(['ticker', 'date']).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).reset_index()
    
    daily = daily.sort_values(['ticker', 'date'])
    
    # Calcular ATR por ticker (vectorizado)
    results = []
    for ticker in daily['ticker'].unique():
        df_ticker = daily[daily['ticker'] == ticker].copy()
        
        # True Range
        df_ticker['prev_close'] = df_ticker['close'].shift(1)
        df_ticker['tr'] = df_ticker.apply(lambda row: max(
            row['high'] - row['low'],
            abs(row['high'] - row['prev_close']) if pd.notna(row['prev_close']) else 0,
            abs(row['low'] - row['prev_close']) if pd.notna(row['prev_close']) else 0
        ), axis=1)
        
        # ATR(14) - rolling mean
        df_ticker['atr'] = df_ticker['tr'].rolling(window=14, min_periods=14).mean()
        
        # EMA(20)
        df_ticker['ema20'] = df_ticker['close'].ewm(span=20, adjust=False).mean()
        
        # Rango diario
        df_ticker['daily_range_pct'] = (df_ticker['high'] - df_ticker['low']) / df_ticker['open']
        
        # Filtrar solo con ATR/EMA válidos
        df_ticker = df_ticker.dropna(subset=['atr', 'ema20'])
        
        results.append(df_ticker[['ticker', 'date', 'open', 'atr', 'ema20', 'daily_range_pct']])
    
    df_regime = pd.concat(results, ignore_index=True)
    
    # Convertir date a datetime para merge
    df_regime['date'] = pd.to_datetime(df_regime['date'])
    
    # Merge con forecast para obtener prob_win y side
    df_regime = df_regime.merge(
        forecast[['ticker', 'date', 'prob_win']],
        on=['ticker', 'date'],
        how='inner'
    )
    
    # Determinar side y direccionalidad
    df_regime['side'] = df_regime['prob_win'].apply(lambda x: 'BUY' if x > 0.5 else 'SELL')
    df_regime['is_directional'] = (
        ((df_regime['open'] > df_regime['ema20']) & (df_regime['side'] == 'BUY')) |
        ((df_regime['open'] < df_regime['ema20']) & (df_regime['side'] == 'SELL'))
    )
    
    # Calcular percentil 75 de ATR por ticker
    atr_p75 = df_regime.groupby('ticker')['atr'].quantile(0.75).to_dict()
    df_regime['atr_threshold'] = df_regime['ticker'].map(atr_p75)
    df_regime['is_high_vol'] = df_regime['atr'] > df_regime['atr_threshold']
    
    # Filtro de rango amplio
    df_regime['is_wide_range'] = df_regime['daily_range_pct'] > 0.015
    
    print(f"[INFO] Régimen calculado para {len(df_regime)} ticker-fechas")
    print(f"  - High vol: {df_regime['is_high_vol'].sum()} ({df_regime['is_high_vol'].mean()*100:.1f}%)")
    print(f"  - Wide range: {df_regime['is_wide_range'].sum()} ({df_regime['is_wide_range'].mean()*100:.1f}%)")
    print(f"  - Directional: {df_regime['is_directional'].sum()} ({df_regime['is_directional'].mean()*100:.1f}%)")
    
    return df_regime


def filter_time_windows(df_candles, windows):
    """
    Filtra candles que están dentro de las ventanas de tiempo permitidas.
    
    Args:
        df_candles: DataFrame con columna 'datetime'
        windows: Lista de tuplas (start_time, end_time)
    
    Returns:
        DataFrame filtrado
    """
    mask = pd.Series([False] * len(df_candles), index=df_candles.index)
    
    for start_time, end_time in windows:
        time_mask = (df_candles['datetime'].dt.time >= start_time) & \
                   (df_candles['datetime'].dt.time <= end_time)
        mask |= time_mask
    
    return df_candles[mask].copy()


def find_ema20_pullback_entry(df_window, side):
    """
    Busca entrada por pullback a EMA20 dentro de la ventana.

    BUY: low <= EMA20 y close > EMA20 (reclaim)
    SELL: high >= EMA20 y close < EMA20 (rejection)

    Returns:
        (entry_price, entry_time, entry_idx) o (None, None, None)
    """
    if len(df_window) < 20:
        return None, None, None

    df_window = df_window.copy()
    df_window['ema20_intraday'] = df_window['close'].ewm(span=20, adjust=False).mean()

    if side == 'BUY':
        signal_mask = (df_window['low'] <= df_window['ema20_intraday']) & (df_window['close'] > df_window['ema20_intraday'])
    else:  # SELL
        signal_mask = (df_window['high'] >= df_window['ema20_intraday']) & (df_window['close'] < df_window['ema20_intraday'])

    if not signal_mask.any():
        return None, None, None

    entry_idx = signal_mask.idxmax()
    entry_candle = df_window.loc[entry_idx]
    entry_price = entry_candle['close']
    entry_time = entry_candle['datetime']
    return entry_price, entry_time, entry_idx


def simulate_trade(df_day, entry_price, side, tp_distance, sl_distance, capital, position_pct):
    """
    Simula un trade intraday con SL/TP adaptativos.
    
    Args:
        df_day: DataFrame con candles del día (filtrados por ventana de tiempo)
        entry_price: Precio de entrada
        side: 'BUY' o 'SELL'
        tp_distance: Distancia al TP en dólares (ej: 1.5 * ATR)
        sl_distance: Distancia al SL en dólares (ej: 0.75 * ATR)
        capital: Capital disponible
        position_pct: % del capital a usar (default 0.10)
    
    Returns:
        dict con resultado del trade o None si no se ejecuta
    """
    qty = int((capital * position_pct) / entry_price)
    if qty == 0:
        return None
    
    # Calcular niveles TP/SL
    if side == 'BUY':
        tp_price = entry_price + tp_distance
        sl_price = entry_price - sl_distance
    else:  # SELL
        tp_price = entry_price - tp_distance
        sl_price = entry_price + sl_distance
    
    # Verificar cada candle
    for idx, candle in df_day.iterrows():
        high = candle['high']
        low = candle['low']
        
        # Check TP
        if side == 'BUY' and high >= tp_price:
            pnl = (tp_price - entry_price) * qty
            return {
                'exit_price': tp_price,
                'exit_time': candle['datetime'],
                'exit_reason': 'TP',
                'pnl': pnl,
                'qty': qty
            }
        elif side == 'SELL' and low <= tp_price:
            pnl = (entry_price - tp_price) * qty
            return {
                'exit_price': tp_price,
                'exit_time': candle['datetime'],
                'exit_reason': 'TP',
                'pnl': pnl,
                'qty': qty
            }
        
        # Check SL
        if side == 'BUY' and low <= sl_price:
            pnl = (sl_price - entry_price) * qty
            return {
                'exit_price': sl_price,
                'exit_time': candle['datetime'],
                'exit_reason': 'SL',
                'pnl': pnl,
                'qty': qty
            }
        elif side == 'SELL' and high >= sl_price:
            pnl = (entry_price - sl_price) * qty
            return {
                'exit_price': sl_price,
                'exit_time': candle['datetime'],
                'exit_reason': 'SL',
                'pnl': pnl,
                'qty': qty
            }
    
    # Timeout (EOD)
    last_candle = df_day.iloc[-1]
    exit_price = last_candle['close']
    
    if side == 'BUY':
        pnl = (exit_price - entry_price) * qty
    else:
        pnl = (entry_price - exit_price) * qty
    
    return {
        'exit_price': exit_price,
        'exit_time': last_candle['datetime'],
        'exit_reason': 'TIMEOUT',
        'pnl': pnl,
        'qty': qty
    }


def simulate_trades_v2(df_intraday, forecast, df_regime, initial_capital, position_pct=0.25, 
                       max_trades_per_window=5, tp_multiplier=1.5, sl_multiplier=0.75,
                       prob_win_threshold=0.55, skip_regime_filters=False, num_windows=3,
                       entry_pattern="window_open"):
    """
    Simula trades intraday con filtros configurables (v2).
    
    Features:
    - Time gating: 3-5 ventanas configurables
    - Máximo N trades por ventana (configurable)
    - Filtros de régimen opcionales
    - SL/TP adaptativo basado en ATR
    - Señales con prob_win > threshold (configurable)
    """
    # Definir todas las ventanas posibles en UTC
    # 9:30-10:30 ET = 14:30-15:30 UTC (apertura)
    # 11:00-12:00 ET = 16:00-17:00 UTC (mañana)
    # 12:00-13:00 ET = 17:00-18:00 UTC (mediodía)
    # 13:00-14:00 ET = 18:00-19:00 UTC (tarde)
    # 14:00-15:00 ET = 19:00-20:00 UTC (cierre)
    ALL_WINDOWS = [
        (time(14, 30), time(15, 30)),   # Apertura
        (time(16, 0), time(17, 0)),     # Mañana
        (time(17, 0), time(18, 0)),     # Mediodía
        (time(18, 0), time(19, 0)),     # Tarde
        (time(19, 0), time(20, 0))      # Cierre
    ]
    
    # Seleccionar ventanas según configuración
    if num_windows == 5:
        TIME_WINDOWS = ALL_WINDOWS
    elif num_windows == 4:
        TIME_WINDOWS = [ALL_WINDOWS[0], ALL_WINDOWS[1], ALL_WINDOWS[2], ALL_WINDOWS[4]]  # Skip tarde
    elif num_windows == 3:
        TIME_WINDOWS = [ALL_WINDOWS[0], ALL_WINDOWS[2], ALL_WINDOWS[4]]  # Apertura, mediodía, cierre
    else:
        TIME_WINDOWS = [ALL_WINDOWS[0], ALL_WINDOWS[4]]  # Solo apertura y cierre
    
    # Merge forecast con régimen
    forecast_filtered = forecast.merge(
        df_regime[['ticker', 'date', 'atr', 'is_high_vol', 'is_wide_range', 'is_directional', 'side']],
        left_on=['ticker', 'date'],
        right_on=['ticker', 'date'],
        how='inner'
    )
    
    # Filtros configurables
    if skip_regime_filters:
        # Solo prob_win (modo agresivo)
        forecast_filtered = forecast_filtered[
            (forecast_filtered['prob_win'] > prob_win_threshold)
        ].copy()
    else:
        # Con filtros de régimen (modo balanceado)
        forecast_filtered = forecast_filtered[
            (forecast_filtered['prob_win'] > prob_win_threshold) &
            (
                (forecast_filtered['is_high_vol'] == True) |
                (forecast_filtered['is_wide_range'] == True)
            )
        ].copy()
    
    print(f"[INFO] Señales después de filtros estrictos: {len(forecast_filtered)}")
    
    # Agrupar intraday por (ticker, date) - usar dict precomputado
    # NOTA: df_intraday ya tiene columna 'date' creada en main()
    print("[INFO] Agrupando datos intraday por ticker-fecha...")
    prices_by_ticker_date = {}
    
    for (ticker, date), group in df_intraday.groupby(['ticker', 'date']):
        # Filtrar por ventanas de tiempo
        group_filtered = filter_time_windows(group, TIME_WINDOWS)
        if len(group_filtered) > 0:
            prices_by_ticker_date[(ticker, date)] = group_filtered.sort_values('datetime')
    
    trades = []
    capital = initial_capital
    
    # Contador de trades por ventana
    trades_per_window = {}  # key: (ticker, date, window_idx)
    
    # Debug counters
    no_intraday_data = 0
    no_window_data = 0
    zero_qty = 0
    
    for idx, row in forecast_filtered.iterrows():
        ticker = row['ticker']
        date = pd.to_datetime(row['date']).date()
        prob_win = row['prob_win']
        atr = row['atr']
        side = row['side']
        
        key = (ticker, date)
        if key not in prices_by_ticker_date:
            no_intraday_data += 1
            continue
        
        df_day = prices_by_ticker_date[key]
        
        # Dividir día por ventanas
        for window_idx, (start_time, end_time) in enumerate(TIME_WINDOWS):
            window_key = (ticker, date, window_idx)
            
            # Check límite de trades por ventana
            if trades_per_window.get(window_key, 0) >= max_trades_per_window:
                continue
            
            # Filtrar candles de esta ventana
            mask_window = (df_day['datetime'].dt.time >= start_time) & \
                         (df_day['datetime'].dt.time <= end_time)
            df_window = df_day[mask_window].copy()
            
            if len(df_window) == 0:
                no_window_data += 1
                continue
            
            # Entry según patrón
            if entry_pattern == "ema20_pullback":
                entry_price, entry_time, entry_idx = find_ema20_pullback_entry(df_window, side)
                if entry_price is None:
                    continue
                df_after_entry = df_window.loc[entry_idx:].copy()
                if len(df_after_entry) <= 1:
                    continue
                df_sim = df_after_entry.iloc[1:]
            else:
                entry_candle = df_window.iloc[0]
                entry_price = entry_candle['open']
                entry_time = entry_candle['datetime']
                df_sim = df_window.iloc[1:]
            
            # Calcular TP/SL adaptativo
            tp_distance = tp_multiplier * atr
            sl_distance = sl_multiplier * atr
            
            # Calcular qty
            qty = int((capital * position_pct) / entry_price)
            if qty == 0:
                zero_qty += 1
                continue
            
            # Simular trade
            result = simulate_trade(
                df_sim,
                entry_price,
                side,
                tp_distance,
                sl_distance,
                capital,
                position_pct
            )
            
            if result is None:
                continue
            
            # Actualizar capital
            capital += result['pnl']
            
            # Registrar trade
            trades.append({
                'ticker': ticker,
                'date': date,
                'side': side,
                'entry_price': entry_price,
                'exit_price': result['exit_price'],
                'entry_time': entry_time,
                'exit_time': result['exit_time'],
                'exit_reason': result['exit_reason'],
                'qty': result['qty'],
                'pnl': result['pnl'],
                'capital': capital,
                'prob_win': prob_win,
                'atr': atr,
                'tp_distance': tp_distance,
                'sl_distance': sl_distance,
                'window': f"{start_time}-{end_time}"
            })
            
            # Incrementar contador de ventana
            trades_per_window[window_key] = trades_per_window.get(window_key, 0) + 1
            
            # Solo 1 trade por ticker-fecha (primer ventana válida)
            break
    
    print(f"[INFO] Total trades simulados: {len(trades)}")
    if no_intraday_data > 0:
        print(f"[DEBUG] Señales sin datos intraday: {no_intraday_data}")
    if no_window_data > 0:
        print(f"[DEBUG] Ventanas sin candles: {no_window_data}")
    if zero_qty > 0:
        print(f"[DEBUG] Trades con qty=0 (precio muy alto): {zero_qty}")
    
    return trades


def main():
    parser = argparse.ArgumentParser(description='Generador de trades intraday v2 (filtros estrictos)')
    parser.add_argument('--capital', type=float, required=True, help='Capital inicial')
    parser.add_argument('--tp-multiplier', type=float, default=1.5, help='Multiplicador ATR para TP (default: 1.5)')
    parser.add_argument('--sl-multiplier', type=float, default=0.75, help='Multiplicador ATR para SL (default: 0.75)')
    parser.add_argument('--intraday', type=str, required=True, help='Path a consolidated_15m.parquet')
    parser.add_argument('--forecast', type=str, default='data/daily/forecast_prob_win.parquet', help='Path a forecast')
    parser.add_argument('--output-dir', type=str, required=True, help='Directorio de salida')
    parser.add_argument('--start-date', type=str, default='2022-02-01', help='Fecha inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2025-12-31', help='Fecha fin (YYYY-MM-DD)')
    parser.add_argument('--max-trades-per-window', type=int, default=5, help='Máx trades por ventana')
    parser.add_argument('--position-pct', type=float, default=0.25, help='% capital por trade')
    parser.add_argument('--prob-win-threshold', type=float, default=0.55, help='Threshold mínimo prob_win')
    parser.add_argument('--skip-regime-filters', action='store_true', help='Desactivar filtros de régimen (solo prob_win)')
    parser.add_argument('--num-windows', type=int, default=3, help='Número de ventanas horarias (3, 4 o 5)')
    parser.add_argument('--entry-pattern', type=str, default='window_open', choices=['window_open', 'ema20_pullback'],
                        help='Patrón de entrada (default: window_open)')
    
    args = parser.parse_args()
    
    mode = "AGGRESSIVE" if args.skip_regime_filters else "BALANCED"
    print(f"\n{'='*70}")
    print(f"INTRADAY SIMULATOR V2 - {mode} MODE")
    print(f"{'='*70}")
    print(f"Capital inicial: ${args.capital:,.2f}")
    print(f"TP: {args.tp_multiplier}x ATR | SL: {args.sl_multiplier}x ATR")
    print(f"Prob Win Threshold: {args.prob_win_threshold:.2f}")
    print(f"Filtros régimen: {'NO' if args.skip_regime_filters else 'SÍ'}")
    print(f"Ventanas horarias: {args.num_windows}")
    print(f"Max trades/ventana: {args.max_trades_per_window}")
    print(f"Posición: {args.position_pct*100:.0f}% capital")
    print(f"Patrón entrada: {args.entry_pattern}")
    print(f"Período: {args.start_date} a {args.end_date}")
    print(f"{'='*70}\n")
    
    # Cargar datos
    print("[1/5] Cargando datos...")
    df_intraday = pd.read_parquet(args.intraday)
    # Renombrar timestamp -> datetime si existe
    if 'timestamp' in df_intraday.columns:
        df_intraday.rename(columns={'timestamp': 'datetime'}, inplace=True)
    df_intraday['datetime'] = pd.to_datetime(df_intraday['datetime'])
    print(f"  ✓ Intraday: {len(df_intraday):,} candles 15m")
    
    forecast = pd.read_parquet(args.forecast)
    forecast['date'] = pd.to_datetime(forecast['date'])
    print(f"  ✓ Forecast: {len(forecast):,} señales")
    
    # Filtrar por fecha
    start_dt = pd.to_datetime(args.start_date)
    end_dt = pd.to_datetime(args.end_date)
    forecast = forecast[(forecast['date'] >= start_dt) & (forecast['date'] <= end_dt)].copy()
    print(f"  ✓ Forecast filtrado: {len(forecast):,} señales")
    
    # Calcular régimen
    print("\n[2/5] Calculando filtros de régimen...")
    # Preparar columna date (solo una vez)
    df_intraday['date'] = df_intraday['datetime'].dt.date
    df_regime = calculate_regime_filters(df_intraday, forecast)
    
    # Simular trades
    mode_label = "agresivos" if args.skip_regime_filters else "semi-estrictos"
    print(f"\n[3/5] Simulando trades con filtros {mode_label}...")
    trades = simulate_trades_v2(
        df_intraday,
        forecast,
        df_regime,
        args.capital,
        position_pct=args.position_pct,
        max_trades_per_window=args.max_trades_per_window,
        tp_multiplier=args.tp_multiplier,
        sl_multiplier=args.sl_multiplier,
        prob_win_threshold=args.prob_win_threshold,
        skip_regime_filters=args.skip_regime_filters,
        num_windows=args.num_windows,
        entry_pattern=args.entry_pattern
    )
    
    if len(trades) == 0:
        print("\n[ERROR] No se generaron trades. Revisa filtros.")
        return
    
    # Convertir a DataFrame
    df_trades = pd.DataFrame(trades)
    
    # Calcular métricas
    print("\n[4/5] Calculando métricas...")
    total_pnl = df_trades['pnl'].sum()
    final_capital = args.capital + total_pnl
    roi = (total_pnl / args.capital) * 100
    
    wins = df_trades[df_trades['pnl'] > 0]
    losses = df_trades[df_trades['pnl'] < 0]
    
    win_rate = len(wins) / len(df_trades) * 100 if len(df_trades) > 0 else 0
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0
    
    total_wins_pnl = wins['pnl'].sum() if len(wins) > 0 else 0
    total_losses_pnl = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
    profit_factor = total_wins_pnl / total_losses_pnl if total_losses_pnl > 0 else 0
    
    exit_breakdown = df_trades['exit_reason'].value_counts().to_dict()
    
    # Guardar resultados
    print("\n[5/5] Guardando resultados...")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # CSV de trades
    csv_path = output_dir / 'all_trades.csv'
    df_trades.to_csv(csv_path, index=False)
    print(f"  ✓ Trades: {csv_path}")
    
    # Summary JSON
    summary = {
        'config': {
            'capital': args.capital,
            'tp_multiplier': args.tp_multiplier,
            'sl_multiplier': args.sl_multiplier,
            'max_trades_per_window': args.max_trades_per_window,
            'position_pct': args.position_pct,
            'entry_pattern': args.entry_pattern,
            'start_date': args.start_date,
            'end_date': args.end_date
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
            'exit_breakdown': exit_breakdown
        }
    }
    
    json_path = output_dir / 'summary.json'
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ Summary: {json_path}")
    
    # Mostrar resumen
    print(f"\n{'='*70}")
    print(f"RESULTADOS FINALES")
    print(f"{'='*70}")
    print(f"Total Trades: {len(df_trades):,}")
    print(f"Total P&L: ${total_pnl:,.2f}")
    print(f"Final Capital: ${final_capital:,.2f}")
    print(f"ROI: {roi:+.2f}%")
    print(f"Win Rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"Profit Factor: {profit_factor:.2f}x")
    print(f"Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
    print(f"\nExit Breakdown:")
    for reason, count in exit_breakdown.items():
        pct = count / len(df_trades) * 100
        print(f"  {reason}: {count:,} ({pct:.1f}%)")
    print(f"{'='*70}")
    
    # Objetivo PF >= 1.15
    if profit_factor >= 1.15:
        print(f"✅ OBJETIVO CUMPLIDO: PF {profit_factor:.2f}x >= 1.15x")
    else:
        gap = 1.15 - profit_factor
        print(f"❌ OBJETIVO NO CUMPLIDO: PF {profit_factor:.2f}x < 1.15x (falta {gap:.2f}x)")
    
    print(f"\n✓ Resultados guardados en: {output_dir}")


if __name__ == '__main__':
    main()
