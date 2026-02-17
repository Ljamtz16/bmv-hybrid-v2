# =============================================
# 09_make_targets_intraday.py
# =============================================
"""
Calcula targets y features para datos intraday.

Targets:
- ret_30m, ret_60m, ret_120m: retornos futuros
- win: 1 si se toca TP antes que SL dentro de la sesión
- tte_bars: barras hasta tocar TP o SL
- hit_type: 'TP', 'SL', 'EOD', 'NONE'

Features:
- Técnicos: RSI, EMA, MACD, ATR, Bollinger, volumen
- Liquidez: spread estimado, turnover, volumen relativo
- Contexto: hora del día, distancia a open/close

Uso:
  python scripts/09_make_targets_intraday.py --date 2025-11-03 --interval 15m
  python scripts/09_make_targets_intraday.py --start 2025-10-01 --end 2025-10-31 --interval 15m
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yaml


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Fecha única YYYY-MM-DD")
    ap.add_argument("--start", help="Fecha inicio YYYY-MM-DD (rango)")
    ap.add_argument("--end", help="Fecha fin YYYY-MM-DD (rango)")
    ap.add_argument("--interval", default="15m", help="Intervalo de velas")
    ap.add_argument("--config", default="config/intraday.yaml", help="Archivo de configuración")
    ap.add_argument("--intraday-dir", default="data/intraday", help="Directorio de datos intraday")
    ap.add_argument("--out-dir", default="features/intraday", help="Directorio de salida")
    # TRAINING PARAMS (conservadores para mejor balance): TP=1.2-1.5%, SL=0.3-0.5%, horizon=8-12 bars
    ap.add_argument("--tp-pct", type=float, default=0.012, help="Take profit % (training, conservador)")
    ap.add_argument("--sl-pct", type=float, default=0.003, help="Stop loss % (training, conservador)")
    ap.add_argument("--horizon-bars", type=int, default=10, help="Horizon en barras (2-3 horas)")
    return ap.parse_args()


def load_config(config_path):
    """Cargar configuración si existe."""
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def get_date_range(args):
    """Obtener lista de fechas a procesar."""
    if args.date:
        return [datetime.fromisoformat(args.date)]
    elif args.start and args.end:
        start = datetime.fromisoformat(args.start)
        end = datetime.fromisoformat(args.end)
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)
        return dates
    else:
        raise ValueError("Debe especificar --date o --start/--end")


def load_intraday_data(date_str, intraday_dir):
    """Cargar todos los tickers para una fecha."""
    date_dir = Path(intraday_dir) / date_str
    if not date_dir.exists():
        print(f"[targets_intraday] WARN: No existe {date_dir}")
        return None
    
    files = list(date_dir.glob("*.parquet"))
    if not files:
        print(f"[targets_intraday] WARN: No hay archivos en {date_dir}")
        return None
    
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            print(f"[targets_intraday] ERROR leyendo {f}: {e}")
    
    if not dfs:
        return None
    
    combined = pd.concat(dfs, ignore_index=True)
    combined['timestamp'] = pd.to_datetime(combined['timestamp'])
    combined = combined.sort_values(['ticker', 'timestamp'])
    return combined


def calculate_technical_features(df):
    """Calcular features técnicos por ticker."""
    features = df.copy()
    
    # RSI
    for period in [7, 14]:
        delta = features['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        features[f'RSI_{period}'] = 100 - (100 / (1 + rs))
    
    # EMAs
    for period in [9, 20, 50]:
        features[f'EMA_{period}'] = features['close'].ewm(span=period, adjust=False).mean()
    
    # MACD
    ema12 = features['close'].ewm(span=12, adjust=False).mean()
    ema26 = features['close'].ewm(span=26, adjust=False).mean()
    features['MACD'] = ema12 - ema26
    features['MACD_signal'] = features['MACD'].ewm(span=9, adjust=False).mean()
    features['MACD_hist'] = features['MACD'] - features['MACD_signal']
    
    # ATR
    high_low = features['high'] - features['low']
    high_close = np.abs(features['high'] - features['close'].shift())
    low_close = np.abs(features['low'] - features['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    features['ATR_14'] = tr.rolling(window=14).mean()
    features['ATR_pct'] = features['ATR_14'] / features['close']
    
    # Bollinger Bands
    features['BB_middle'] = features['close'].rolling(window=20).mean()
    bb_std = features['close'].rolling(window=20).std()
    features['BB_upper'] = features['BB_middle'] + (bb_std * 2)
    features['BB_lower'] = features['BB_middle'] - (bb_std * 2)
    features['BB_width'] = (features['BB_upper'] - features['BB_lower']) / features['BB_middle']
    
    # Volumen
    features['volume_ma_20'] = features['volume'].rolling(window=20).mean()
    features['volume_ratio'] = features['volume'] / (features['volume_ma_20'] + 1)
    features['volume_zscore'] = (features['volume'] - features['volume'].rolling(window=20).mean()) / (features['volume'].rolling(window=20).std() + 1e-10)
    
    # VWAP
    features['VWAP'] = (features['close'] * features['volume']).cumsum() / features['volume'].cumsum()
    features['VWAP_dev'] = (features['close'] - features['VWAP']) / features['VWAP']
    
    return features


def calculate_liquidity_features(df):
    """Calcular features de liquidez."""
    features = df.copy()
    
    # Spread estimado (high-low como proxy)
    features['spread_pct'] = (features['high'] - features['low']) / features['close']
    features['spread_bps'] = features['spread_pct'] * 10000
    
    # Turnover
    features['turnover'] = features['volume'] * features['close']
    features['turnover_ma_20'] = features['turnover'].rolling(window=20).mean()
    features['turnover_ratio'] = features['turnover'] / (features['turnover_ma_20'] + 1)
    
    return features


def calculate_time_features(df):
    """Calcular features de contexto temporal."""
    features = df.copy()
    
    # Hora del día
    features['hour'] = features['timestamp'].dt.hour
    features['minute'] = features['timestamp'].dt.minute
    features['time_numeric'] = features['hour'] + features['minute'] / 60
    
    # Distancia a apertura/cierre (asumiendo 9:30-16:00)
    market_open = 9.5  # 9:30
    market_close = 16.0
    features['dist_to_open'] = features['time_numeric'] - market_open
    features['dist_to_close'] = market_close - features['time_numeric']
    
    # Primera/última hora
    features['is_first_hour'] = (features['dist_to_open'] <= 1).astype(int)
    features['is_last_hour'] = (features['dist_to_close'] <= 1).astype(int)
    
    return features


def detect_direction(df):
    """
    Detectar dirección de trade (LONG o SHORT) basado en indicadores.
    
    Señales LONG:
    - Precio > EMA_50
    - RSI < 70 (no sobrecomprado)
    - MACD > 0
    - Close > BB_lower
    
    Señales SHORT:
    - Precio < EMA_50
    - RSI > 30 (no sobrevendido)
    - MACD < 0
    - Close < BB_upper
    """
    direction = pd.Series('LONG', index=df.index)
    
    # Condiciones para SHORT
    short_conditions = (
        (df['close'] < df['EMA_50']) &
        (df['RSI_14'] > 30) &
        (df['MACD'] < 0) &
        (df['close'] < df['BB_upper'])
    )
    
    direction[short_conditions] = 'SHORT'
    
    return direction


def calculate_targets(df, tp_pct, sl_pct, horizon_bars=None):
    """Calcular targets: retornos futuros y TP/SL hits para LONG y SHORT.
    
    Args:
        df: DataFrame con datos OHLCV
        tp_pct: Take profit % (e.g., 0.012 = 1.2%)
        sl_pct: Stop loss % (e.g., 0.003 = 0.3%)
        horizon_bars: Máximo de barras para buscar hit (None = hasta EOD)
    """
    targets = df.copy()
    
    # Detectar dirección
    targets['direction'] = detect_direction(targets)
    
    # Retornos futuros (en número de barras adelante)
    # Para 15m: 2 barras = 30m, 4 barras = 60m, 8 barras = 120m
    for bars in [2, 4, 8]:
        minutes = bars * 15
        col_name = f'ret_{minutes}m'
        targets[col_name] = (targets['close'].shift(-bars) / targets['close'] - 1)
    
    # TP/SL hit detection
    entry_price = targets['close']
    
    # Para LONG: TP arriba, SL abajo
    tp_price_long = entry_price * (1 + tp_pct)
    sl_price_long = entry_price * (1 - sl_pct)
    
    # Para SHORT: TP abajo, SL arriba (invertido)
    tp_price_short = entry_price * (1 - tp_pct)
    sl_price_short = entry_price * (1 + sl_pct)
    
    # Inicializar columnas
    targets['win'] = 0
    targets['tte_bars'] = np.nan
    targets['hit_type'] = 'NONE'
    
    # Para cada fila, buscar hacia adelante hasta EOD o hit
    for idx in range(len(targets)):
        if idx >= len(targets) - 1:
            continue
        
        entry = entry_price.iloc[idx]
        direction = targets['direction'].iloc[idx]
        current_date = targets['timestamp'].iloc[idx].date()
        
        # Seleccionar TP/SL según dirección
        if direction == 'LONG':
            tp = tp_price_long.iloc[idx]
            sl = sl_price_long.iloc[idx]
        else:  # SHORT
            tp = tp_price_short.iloc[idx]
            sl = sl_price_short.iloc[idx]
        
        # Buscar hacia adelante en el mismo día (con límite de horizon_bars si aplica)
        future_idx = idx + 1
        bars_to_hit = 0
        hit = 'NONE'
        
        while future_idx < len(targets):
            future_row = targets.iloc[future_idx]
            
            # Si cambió de día, break
            if future_row['timestamp'].date() != current_date:
                hit = 'EOD'
                break
            
            bars_to_hit += 1
            
            # Si alcanzamos el horizon, break (training conservador)
            if horizon_bars is not None and bars_to_hit > horizon_bars:
                hit = 'HORIZON'
                break
            high = future_row['high']
            low = future_row['low']
            
            # Check TP/SL según dirección
            if direction == 'LONG':
                # LONG: TP arriba, SL abajo
                if high >= tp:
                    hit = 'TP'
                    break
                if low <= sl:
                    hit = 'SL'
                    break
            else:  # SHORT
                # SHORT: TP abajo, SL arriba (invertido)
                if low <= tp:
                    hit = 'TP'
                    break
                if high >= sl:
                    hit = 'SL'
                    break
            
            future_idx += 1
            
            # Límite de búsqueda (26 barras = 1 día de trading)
            if bars_to_hit > 26:
                hit = 'EOD'
                break
        
        # Asignar resultados
        targets.at[idx, 'hit_type'] = hit
        targets.at[idx, 'tte_bars'] = bars_to_hit if hit != 'NONE' else np.nan
        targets.at[idx, 'win'] = 1 if hit == 'TP' else 0
    
    return targets


def process_ticker(ticker_df, tp_pct, sl_pct, horizon_bars=None):
    """Procesar un ticker completo."""
    # Ordenar por timestamp
    ticker_df = ticker_df.sort_values('timestamp').reset_index(drop=True)
    
    # Features técnicos
    ticker_df = calculate_technical_features(ticker_df)
    
    # Features de liquidez
    ticker_df = calculate_liquidity_features(ticker_df)
    
    # Features de tiempo
    ticker_df = calculate_time_features(ticker_df)
    
    # Targets
    ticker_df = calculate_targets(ticker_df, tp_pct, sl_pct, horizon_bars)
    
    return ticker_df


def main():
    args = parse_args()
    config = load_config(args.config)
    
    # Parámetros (training conservadores)
    tp_pct = args.tp_pct if args.tp_pct else config.get('risk', {}).get('tp_pct_train', 0.012)
    sl_pct = args.sl_pct if args.sl_pct else config.get('risk', {}).get('sl_pct_train', 0.003)
    horizon_bars = args.horizon_bars if hasattr(args, 'horizon_bars') else config.get('training', {}).get('horizon_bars', 10)
    
    print(f"[targets_intraday] TRAINING params: TP={tp_pct:.3%}, SL={sl_pct:.3%}, Horizon={horizon_bars} bars")
    
    # Obtener fechas
    dates = get_date_range(args)
    print(f"[targets_intraday] Procesando {len(dates)} fechas")
    
    # Procesar cada fecha
    for date in dates:
        date_str = date.strftime('%Y-%m-%d')
        print(f"\n[targets_intraday] Procesando {date_str}")
        
        # Cargar datos
        df = load_intraday_data(date_str, args.intraday_dir)
        if df is None or df.empty:
            continue
        
        # Procesar por ticker
        results = []
        tickers = df['ticker'].unique()
        for ticker in tickers:
            ticker_df = df[df['ticker'] == ticker].copy()
            try:
                processed = process_ticker(ticker_df, tp_pct, sl_pct, horizon_bars)
                results.append(processed)
                print(f"[targets_intraday]   {ticker}: {len(processed)} barras, {processed['win'].sum()} wins")
            except Exception as e:
                print(f"[targets_intraday]   ERROR {ticker}: {e}")
        
        if not results:
            continue
        
        # Combinar y guardar
        combined = pd.concat(results, ignore_index=True)
        
        # Remover filas con NaN en features clave (warmup)
        combined = combined.dropna(subset=['RSI_14', 'EMA_20', 'MACD', 'ATR_14'])
        
        # Guardar
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{date_str}.parquet"
        combined.to_parquet(out_file, index=False)
        
        print(f"[targets_intraday] Guardado {out_file} ({len(combined)} filas)")
        print(f"[targets_intraday]   Win rate: {combined['win'].mean():.2%}")
        print(f"[targets_intraday]   TP hits: {(combined['hit_type']=='TP').sum()}")
        print(f"[targets_intraday]   SL hits: {(combined['hit_type']=='SL').sum()}")
        print(f"[targets_intraday]   EOD: {(combined['hit_type']=='EOD').sum()}")


if __name__ == "__main__":
    main()
