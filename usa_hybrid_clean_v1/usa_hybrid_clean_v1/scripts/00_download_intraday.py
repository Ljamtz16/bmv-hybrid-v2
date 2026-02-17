# =============================================
# 00_download_intraday.py
# =============================================
"""
Descarga datos intraday (15m/1h) para tickers especificados.
Guarda por día y ticker en formato parquet con timestamp NY.

Uso:
  python scripts/00_download_intraday.py --date 2025-11-03 --interval 15m --tickers AMD,NVDA,TSLA
  python scripts/00_download_intraday.py --date 2025-11-03 --interval 15m --tickers-file data/us/tickers_master.csv
"""

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import yfinance as yf
from zoneinfo import ZoneInfo

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    ap.add_argument("--interval", default="15m", choices=["1m", "2m", "5m", "15m", "30m", "1h"], help="Intervalo de velas")
    ap.add_argument("--tickers", help="Tickers separados por comas (AMD,NVDA,...)")
    ap.add_argument("--tickers-file", help="CSV con columna 'ticker'")
    ap.add_argument("--out-dir", default="data/intraday", help="Directorio de salida")
    ap.add_argument("--tz", default="America/New_York", help="Zona horaria del mercado")
    ap.add_argument("--lookback-days", type=int, default=5, help="Días hacia atrás para descargar")
    return ap.parse_args()


def get_ticker_list(args):
    """Obtener lista de tickers desde CLI o archivo."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.tickers_file:
        df = pd.read_csv(args.tickers_file)
        if 'ticker' in df.columns:
            return df['ticker'].dropna().str.upper().unique().tolist()
        else:
            raise ValueError(f"Archivo {args.tickers_file} debe tener columna 'ticker'")
    else:
        raise ValueError("Debe especificar --tickers o --tickers-file")


def download_intraday(ticker, start_dt, end_dt, interval, tz_str):
    """Descargar datos intraday para un ticker."""
    try:
        print(f"[download_intraday] Descargando {ticker} {interval} {start_dt.date()} -> {end_dt.date()}")
        df = yf.download(
            ticker,
            start=start_dt,
            end=end_dt,
            interval=interval,
            progress=False,
            auto_adjust=True
        )
        
        if df is None or df.empty:
            print(f"[download_intraday] WARN {ticker}: sin datos")
            return None
        
        # Si es MultiIndex (intraday de un solo ticker), aplanar
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Normalizar columnas
        df = df.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
        # Asegurar que tenemos las columnas necesarias
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                print(f"[download_intraday] WARN {ticker}: columna '{col}' no encontrada")
                return None
        
        df = df[required_cols].copy()
        
        # Reset index para obtener la columna de tiempo
        df_reset = df.reset_index()
        
        # Identificar columna de timestamp
        time_col = None
        for possible_col in ['Datetime', 'Date', 'Time', 'timestamp']:
            if possible_col in df_reset.columns:
                time_col = possible_col
                break
        
        if time_col is None:
            print(f"[download_intraday] ERROR {ticker}: {df_reset.columns}")
            return None
        
        df = df_reset
        df.rename(columns={time_col: 'timestamp'}, inplace=True)
        
        # Convertir a zona horaria del mercado
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        tz = ZoneInfo(tz_str)
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert(tz)
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert(tz)
        
        # Agregar ticker
        df['ticker'] = ticker
        
        # Remover duplicados y ordenar
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
        
        return df
        
    except Exception as e:
        print(f"[download_intraday] ERROR {ticker}: {e}")
        return None


def save_by_date(df, ticker, out_dir, date_str):
    """Guardar datos agrupados por fecha."""
    # Agrupar por fecha
    df['date'] = df['timestamp'].dt.date.astype(str)
    dates = df['date'].unique()
    
    for date in dates:
        df_date = df[df['date'] == date].copy()
        date_dir = Path(out_dir) / date
        date_dir.mkdir(parents=True, exist_ok=True)
        
        out_file = date_dir / f"{ticker}.parquet"
        df_date.drop(columns=['date']).to_parquet(out_file, index=False)
        print(f"[download_intraday] Guardado {out_file} ({len(df_date)} barras)")


def main():
    args = parse_args()
    
    # Parsear fecha objetivo
    target_date = datetime.fromisoformat(args.date)
    
    # Calcular ventana de descarga (incluir lookback para features)
    start_dt = target_date - timedelta(days=args.lookback_days)
    end_dt = target_date + timedelta(days=1)
    
    # Obtener tickers
    tickers = get_ticker_list(args)
    print(f"[download_intraday] Procesando {len(tickers)} tickers para {args.date} (lookback={args.lookback_days}d)")
    
    # Descargar y guardar
    success_count = 0
    for ticker in tickers:
        df = download_intraday(ticker, start_dt, end_dt, args.interval, args.tz)
        if df is not None and not df.empty:
            save_by_date(df, ticker, args.out_dir, args.date)
            success_count += 1
    
    print(f"[download_intraday] Completado: {success_count}/{len(tickers)} tickers descargados exitosamente")


if __name__ == "__main__":
    main()
