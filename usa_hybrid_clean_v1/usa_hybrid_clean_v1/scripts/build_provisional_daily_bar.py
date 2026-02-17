"""
build_provisional_daily_bar.py
Construye una barra diaria PROVISIONAL para la fecha NY actual usando datos intradía (yfinance 5m) y la agrega al CSV autoridad.

Reglas:
- Si el CSV ya contiene la barra de la fecha NY actual (date_ny == today_ny), no hace nada.
- La fila provisional se marca con columna 'provisional'=1 (otras filas implícitamente 0 / ausente).
- Mapeo de fechas: fila daily date UTC = (ny_date + 1 día) 00:00:00 UTC (consistente con patrón observado).
- OHLC: se calcula de todos los frames intradía disponibles (open primero, close último, high max, low min, volume suma).
- En caso de datos insuficientes (<3 barras) se aborta para evitar ruido.

Limitaciones:
- Los splits/dividendos intradía no se ajustan aquí; se asume yfinance ya entrega precios ajustados.
- Volumen parcial al momento de ejecución (no final definitivo) → la barra provisional puede diferir del cierre real.

Uso:
    python scripts/build_provisional_daily_bar.py
"""
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf
from zoneinfo import ZoneInfo

CSV_PATH = Path('data/us/ohlcv_us_daily.csv')
TICKERS_PATH = Path('data/us/tickers_master.csv')
OUTPUT_BACKUP = Path('data/us/ohlcv_us_daily_backup_before_provisional.csv')
ny = ZoneInfo('America/New_York')

MIN_BARS_REQUIRED = 3  # para evitar barra vacía con datos escasos


def load_tickers():
    if not TICKERS_PATH.exists():
        raise FileNotFoundError(f'No existe {TICKERS_PATH}')
    df = pd.read_csv(TICKERS_PATH)
    col = None
    for c in df.columns:
        if c.lower() in ('ticker','tickers','symbol'): col = c; break
    if col is None:
        raise ValueError('tickers_master.csv sin columna ticker')
    return sorted(df[col].astype(str).str.upper().unique())


def load_csv_authority():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f'No existe {CSV_PATH}')
    df = pd.read_csv(CSV_PATH)
    if 'date' not in df.columns:
        raise ValueError('CSV sin columna date')
    df['date'] = pd.to_datetime(df['date'], utc=True)
    df['date_ny'] = df['date'].dt.tz_convert(ny).dt.date
    return df


def fetch_intraday_for_today(ticker: str, ny_date) -> pd.DataFrame:
    # Descargar barras 5m del día, usando period=2d y filtrar
    data = yf.download(ticker, period='2d', interval='5m', progress=False)
    if data.empty:
        return data
    data = data.tz_localize(None)  # naive
    # Re-localizar a NY para filtrado
    data.index = pd.to_datetime(data.index).tz_localize(ny)
    data['ny_date'] = data.index.date
    today_bars = data[data['ny_date'] == ny_date]
    return today_bars


def build_daily_row(bars: pd.DataFrame, ticker: str, ny_date) -> dict:
    # Calcular OHLCV
    o = float(bars['Open'].iloc[0])
    c = float(bars['Close'].iloc[-1])
    h = float(bars['High'].max())
    l = float(bars['Low'].min())
    v = int(bars['Volume'].sum()) if 'Volume' in bars.columns else 0
    # Mapeo de date (UTC) = (ny_date + 1 día) 00:00 UTC
    date_utc = (pd.Timestamp(ny_date) + pd.Timedelta(days=1)).tz_localize('UTC')
    return {
        'date': date_utc,
        'ticker': ticker,
        'open': o,
        'high': h,
        'low': l,
        'close': c,
        'volume': v,
        'provisional': 1
    }


def main():
    print('============================================================')
    print('CONSTRUYENDO BARRA DIARIA PROVISIONAL')
    print('============================================================')

    today_ny = pd.Timestamp.now(tz=ny).date()
    print(f'[INFO] Fecha NY actual: {today_ny}')

    df_csv = load_csv_authority()
    if (df_csv['date_ny'] == today_ny).any():
        print(f'[SKIP] Ya existe barra para fecha NY={today_ny} en CSV. No se crea provisional.')
        return 0

    tickers = load_tickers()
    rows = []
    missing = []
    for t in tickers:
        bars = fetch_intraday_for_today(t, today_ny)
        if bars.empty or len(bars) < MIN_BARS_REQUIRED:
            missing.append(t)
            continue
        rows.append(build_daily_row(bars, t, today_ny))

    if not rows:
        print('[ABORT] No se pudo construir ninguna barra (datos intradía insuficientes).')
        if missing:
            print(f'        Tickers sin datos suficientes: {missing[:10]}...')
        return 2

    df_new = pd.DataFrame(rows)
    print(f'[INFO] Barras provisionales construidas: {len(df_new)} tickers')
    if missing:
        print(f'[WARN] {len(missing)} tickers sin datos intradía suficientes (ej: {missing[:8]})')

    # Backup antes de agregar
    if not OUTPUT_BACKUP.exists():
        df_csv.to_csv(OUTPUT_BACKUP, index=False)
        print(f'[OK] Backup creado: {OUTPUT_BACKUP}')

    # Concatenar y guardar
    combined = pd.concat([df_csv.drop(columns=['date_ny']), df_new], ignore_index=True)
    # Ordenar por date, ticker
    combined = combined.sort_values(['date','ticker']).reset_index(drop=True)
    combined.to_csv(CSV_PATH, index=False)
    print(f'[OK] CSV actualizado con provisional → {CSV_PATH}')

    # Verificación rápida
    df_check = load_csv_authority()
    max_ny = df_check['date_ny'].max()
    print(f'[VALID] max(date_ny) ahora = {max_ny}')
    if max_ny != today_ny:
        print('[WARN] La fecha NY máxima no coincide con hoy; revisar mapeo.')
    else:
        print('[SUCCESS] Barra provisional disponible para procesos T+1.')

    return 0

if __name__ == '__main__':
    raise SystemExit(main())
