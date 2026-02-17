# =============================================
# 29b_build_intraday_merge.py
# =============================================
"""
Descarga/arma un CSV intradía unificado (datetime,ticker,open,high,low,close,volume)
para un conjunto de tickers y una ventana de fechas.

Uso típico:
  python scripts/29b_build_intraday_merge.py \
    --tickers AMD,NVDA,AAPL \
    --start 2025-11-01 --end 2025-11-05 \
    --interval 15m \
    --out data/us/intraday/_merged_15m.csv
"""

import argparse, os
from datetime import datetime
import pandas as pd
import yfinance as yf


def _parse_date(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return pd.to_datetime(s).to_pydatetime()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True, help="Lista separada por comas, p.ej. AMD,NVDA,AAPL")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    start_dt = _parse_date(args.start)
    end_dt = _parse_date(args.end)

    rows = []
    for t in tickers:
        # Usar '->' ASCII para evitar problemas de encoding en PowerShell
        print(f"[merge_intraday] Bajando {t} {args.interval} {start_dt.date()}->{end_dt.date()}")
        try:
            df = yf.download(t, start=start_dt, end=end_dt, interval=args.interval, progress=False, auto_adjust=True)
        except Exception as e:
            print(f"[merge_intraday] ERROR {t}: {e}")
            df = pd.DataFrame()
        if df is None or df.empty:
            continue
        # Normalizar columnas
        df = df.rename(columns={
            'Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'
        })
        # Asegurar que existen las columnas requeridas
        for col in ['open','high','low','close','volume']:
            if col not in df.columns:
                print(f"[merge_intraday] WARN {t}: columna '{col}' no encontrada")
                df = pd.DataFrame()
                break
        if df.empty:
            continue
        df = df[['open','high','low','close','volume']].copy()
        df.reset_index(inplace=True)
        # Columna tiempo
        time_col = 'Datetime' if 'Datetime' in df.columns else 'Date' if 'Date' in df.columns else None
        if not time_col:
            print(f"[merge_intraday] WARN {t}: no se encontro columna de tiempo")
            continue
        df.rename(columns={time_col:'datetime'}, inplace=True)
        df['ticker'] = t
        rows.append(df)

    if not rows:
        print("[merge_intraday] Sin datos para combinar")
        pd.DataFrame(columns=['datetime','ticker','open','high','low','close','volume']).to_csv(args.out, index=False)
        print(f"[merge_intraday] OUT -> {args.out}")
        return

    out = pd.concat(rows, ignore_index=True)
    
    # Validar que tenemos la columna datetime
    if 'datetime' not in out.columns:
        print("[merge_intraday] WARN: No se pudo construir columna datetime")
        pd.DataFrame(columns=['datetime','ticker','open','high','low','close','volume']).to_csv(args.out, index=False)
        print(f"[merge_intraday] OUT -> {args.out} (rows=0)")
        return
    
    # Ordenar y asegurar tipos
    out['datetime'] = pd.to_datetime(out['datetime'], errors='coerce')
    out = out.dropna(subset=['datetime'])
    
    if out.empty:
        print("[merge_intraday] WARN: Todos los registros tienen datetime invalido")
        pd.DataFrame(columns=['datetime','ticker','open','high','low','close','volume']).to_csv(args.out, index=False)
        print(f"[merge_intraday] OUT -> {args.out} (rows=0)")
        return
    
    out = out.sort_values(['ticker','datetime'])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"[merge_intraday] OUT -> {args.out} (rows={len(out)})")


if __name__ == "__main__":
    main()
