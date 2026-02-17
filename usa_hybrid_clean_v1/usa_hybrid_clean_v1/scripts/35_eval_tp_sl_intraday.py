# =============================================
# 35_eval_tp_sl_intraday.py
# =============================================
"""
Evalúa posiciones intraday cada 15 minutos durante la sesión.

Funciones:
- Descarga precios actuales (15m)
- Verifica TP/SL hits para posiciones OPEN
- Cierre forzado EOD (15:55-16:00 NY)
- Actualiza predictions_log_intraday.csv
- Genera alertas para Telegram

Uso:
  python scripts/35_eval_tp_sl_intraday.py --date 2025-11-03 --interval 15m
  python scripts/35_eval_tp_sl_intraday.py --date 2025-11-03 --close-time 15:55
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import yfinance as yf
import yaml


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Fecha YYYY-MM-DD (default: hoy)")
    ap.add_argument("--interval", default="15m", help="Intervalo de velas")
    ap.add_argument("--predictions-log", default="data/trading/predictions_log_intraday.csv", help="Log de predicciones")
    ap.add_argument("--config", default="config/intraday.yaml", help="Configuración")
    ap.add_argument("--close-time", default="15:55", help="Hora de cierre forzado (HH:MM)")
    ap.add_argument("--notify", action="store_true", help="Enviar notificaciones")
    return ap.parse_args()


def load_config(config_path):
    """Cargar configuración."""
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def get_current_ny_time():
    """Obtener hora actual en NY."""
    ny_tz = ZoneInfo("America/New_York")
    return datetime.now(ny_tz)


def is_market_hours(current_time, config):
    """Verificar si estamos en horario de mercado."""
    market = config.get('market', {})
    open_time = market.get('open', '09:30')
    close_time = market.get('close', '16:00')
    
    market_open = time(*map(int, open_time.split(':')))
    market_close = time(*map(int, close_time.split(':')))
    
    current = current_time.time()
    return market_open <= current <= market_close


def load_open_positions(log_file, date_str):
    """Cargar posiciones abiertas del día."""
    if not os.path.exists(log_file):
        print(f"[eval_intraday] WARN: No existe {log_file}")
        return pd.DataFrame()
    
    df = pd.read_csv(log_file)
    if df.empty:
        return df
    
    # Filtrar posiciones OPEN del día
    df = df[(df['status'] == 'OPEN') & (df['tag'] == date_str)].copy()
    
    print(f"[eval_intraday] Posiciones OPEN: {len(df)}")
    return df


def download_current_prices(tickers, interval='15m', lookback_hours=2):
    """Descargar precios recientes para tickers."""
    if not tickers:
        return pd.DataFrame()
    
    print(f"[eval_intraday] Descargando precios para {len(tickers)} tickers")
    
    prices = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, period='1d', interval=interval, progress=False, auto_adjust=True)
            if df is not None and not df.empty:
                df = df.reset_index()
                # Normalizar nombres de columnas
                df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
                time_col = 'datetime' if 'datetime' in df.columns else 'date' if 'date' in df.columns else df.columns[0]
                df.rename(columns={time_col: 'timestamp'}, inplace=True)
                
                if 'high' in df.columns and 'low' in df.columns and 'close' in df.columns:
                    prices[ticker] = df[['timestamp', 'high', 'low', 'close']].tail(10)  # Últimas barras
        except Exception as e:
            print(f"[eval_intraday] ERROR descargando {ticker}: {e}")
    
    return prices


def check_tp_sl_hits(positions, current_prices, current_time):
    """Verificar hits de TP/SL en posiciones abiertas (LONG y SHORT)."""
    results = []
    
    for idx, pos in positions.iterrows():
        ticker = pos['ticker']
        direction = pos.get('direction', 'LONG')
        entry = pos['entry']
        tp = pos['tp_price']
        sl = pos['sl_price']
        prediction_id = pos['prediction_id']
        
        if ticker not in current_prices:
            # No hay datos actuales
            results.append({
                'prediction_id': prediction_id,
                'ticker': ticker,
                'status': 'OPEN',
                'exit_price': None,
                'pnl_usd': None,
                'notes': 'No price data'
            })
            continue
        
        ticker_prices = current_prices[ticker]
        
        # Verificar cada barra reciente
        hit = None
        exit_price = None
        
        for _, bar in ticker_prices.iterrows():
            high = bar['high']
            low = bar['low']
            close = bar['close']
            
            if direction == 'LONG':
                # LONG: TP arriba, SL abajo
                if high >= tp:
                    hit = 'TP_HIT'
                    exit_price = tp
                    break
                if low <= sl:
                    hit = 'SL_HIT'
                    exit_price = sl
                    break
            else:  # SHORT
                # SHORT: TP abajo, SL arriba (invertido)
                if low <= tp:
                    hit = 'TP_HIT'
                    exit_price = tp
                    break
                if high >= sl:
                    hit = 'SL_HIT'
                    exit_price = sl
                    break
        
        if hit:
            qty = pos.get('qty', 1)
            
            # PnL según dirección
            if direction == 'LONG':
                pnl = (exit_price - entry) * qty
            else:  # SHORT
                pnl = (entry - exit_price) * qty  # Invertido para SHORT
            
            results.append({
                'prediction_id': prediction_id,
                'ticker': ticker,
                'status': hit,
                'exit_price': exit_price,
                'pnl_usd': pnl,
                'exit_timestamp': current_time.isoformat(),
                'notes': f'{direction} {hit} at {current_time.strftime("%H:%M")}'
            })
            
            print(f"[eval_intraday] {ticker} {direction}: {hit} @ ${exit_price:.2f} (PnL: ${pnl:+.2f})")
        else:
            # Aún OPEN
            results.append({
                'prediction_id': prediction_id,
                'ticker': ticker,
                'status': 'OPEN',
                'exit_price': None,
                'pnl_usd': None,
                'notes': 'Still open'
            })
    
    return pd.DataFrame(results)


def force_eod_close(positions, current_prices, current_time):
    """Forzar cierre EOD para todas las posiciones abiertas."""
    results = []
    
    for idx, pos in positions.iterrows():
        ticker = pos['ticker']
        entry = pos['entry']
        prediction_id = pos['prediction_id']
        
        # Obtener precio de cierre actual
        if ticker in current_prices and not current_prices[ticker].empty:
            close_price = current_prices[ticker]['close'].iloc[-1]
        else:
            # Sin datos, usar entry como proxy
            close_price = entry
        
        qty = pos.get('qty', 1)
        pnl = (close_price - entry) * qty
        
        results.append({
            'prediction_id': prediction_id,
            'ticker': ticker,
            'status': 'EOD_CLOSE',
            'exit_price': close_price,
            'pnl_usd': pnl,
            'exit_timestamp': current_time.isoformat(),
            'notes': f'Forced EOD close at {current_time.strftime("%H:%M")}'
        })
        
        print(f"[eval_intraday] {ticker}: EOD_CLOSE @ ${close_price:.2f} (PnL: ${pnl:+.2f})")
    
    return pd.DataFrame(results)


def update_predictions_log(log_file, updates):
    """Actualizar log de predicciones."""
    if updates.empty:
        return
    
    # Cargar log existente
    if os.path.exists(log_file):
        df = pd.read_csv(log_file)
    else:
        print(f"[eval_intraday] WARN: Log no existe, no se puede actualizar")
        return
    
    # Actualizar registros
    for _, update in updates.iterrows():
        pred_id = update['prediction_id']
        status = update['status']
        
        if status != 'OPEN':
            # Actualizar solo si cambió el status
            mask = df['prediction_id'] == pred_id
            if mask.any():
                df.loc[mask, 'status'] = status
                if pd.notna(update.get('exit_price')):
                    df.loc[mask, 'exit_price'] = update['exit_price']
                if pd.notna(update.get('pnl_usd')):
                    df.loc[mask, 'pnl_usd'] = update['pnl_usd']
                if pd.notna(update.get('exit_timestamp')):
                    df.loc[mask, 'status_ts_utc'] = update['exit_timestamp']
                if pd.notna(update.get('notes')):
                    df.loc[mask, 'notes'] = update['notes']
    
    # Guardar
    df.to_csv(log_file, index=False)
    print(f"[eval_intraday] Log actualizado: {log_file}")


def generate_alerts(updates):
    """Generar alertas para posiciones que cambiaron de estado."""
    alerts = []
    
    for _, update in updates.iterrows():
        status = update['status']
        if status in ['TP_HIT', 'SL_HIT', 'EOD_CLOSE']:
            ticker = update['ticker']
            exit_price = update.get('exit_price', 0)
            pnl = update.get('pnl_usd', 0)
            
            emoji = "✅" if status == 'TP_HIT' else "❌" if status == 'SL_HIT' else "⏹️"
            
            alert = f"{emoji} {ticker}: {status} @ ${exit_price:.2f} (PnL: ${pnl:+.2f})"
            alerts.append(alert)
            print(f"[eval_intraday] ALERT: {alert}")
    
    return alerts


def main():
    args = parse_args()
    config = load_config(args.config)
    
    # Fecha y hora actual NY
    current_time = get_current_ny_time()
    date_str = args.date if args.date else current_time.strftime('%Y-%m-%d')
    
    print(f"[eval_intraday] Evaluando {date_str} @ {current_time.strftime('%H:%M:%S')} NY")
    
    # Verificar horario de mercado
    if not is_market_hours(current_time, config):
        print("[eval_intraday] Fuera de horario de mercado")
        return
    
    # Cargar posiciones abiertas
    positions = load_open_positions(args.predictions_log, date_str)
    if positions.empty:
        print("[eval_intraday] No hay posiciones abiertas")
        return
    
    tickers = positions['ticker'].unique().tolist()
    
    # Descargar precios actuales
    current_prices = download_current_prices(tickers, args.interval)
    
    # Verificar si es hora de cierre forzado
    close_hour, close_min = map(int, args.close_time.split(':'))
    force_close = current_time.hour > close_hour or (current_time.hour == close_hour and current_time.minute >= close_min)
    
    if force_close:
        print(f"[eval_intraday] Forzando cierre EOD (>= {args.close_time})")
        updates = force_eod_close(positions, current_prices, current_time)
    else:
        # Check normal TP/SL
        updates = check_tp_sl_hits(positions, current_prices, current_time)
    
    # Actualizar log
    update_predictions_log(args.predictions_log, updates)
    
    # Generar alertas
    alerts = generate_alerts(updates)
    
    # Guardar alertas si hay notificaciones
    if alerts and args.notify:
        alert_file = Path("reports/intraday") / date_str / "alerts.txt"
        alert_file.parent.mkdir(parents=True, exist_ok=True)
        with open(alert_file, 'a', encoding='utf-8') as f:
            for alert in alerts:
                f.write(f"{current_time.strftime('%H:%M:%S')} - {alert}\n")
        print(f"[eval_intraday] Alertas guardadas: {alert_file}")
    
    # Resumen
    n_closed = len(updates[updates['status'] != 'OPEN'])
    n_open = len(updates[updates['status'] == 'OPEN'])
    total_pnl = updates['pnl_usd'].sum() if 'pnl_usd' in updates.columns else 0
    
    print(f"\n[eval_intraday] ===== RESUMEN =====")
    print(f"  Cerradas: {n_closed}")
    print(f"  Abiertas: {n_open}")
    print(f"  PnL total: ${total_pnl:+.2f}")


if __name__ == "__main__":
    main()
