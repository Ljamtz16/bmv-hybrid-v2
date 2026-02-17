import argparse, os, json
import pandas as pd
from pathlib import Path

def compute_unique_trades(df: pd.DataFrame) -> int:
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols
    if 'entry_date' not in df.columns and 'entry_dt' in df.columns:
        df['entry_date'] = df['entry_dt']
    if 'ticker' not in df.columns or 'entry_date' not in df.columns:
        return int(len(df))
    try:
        # normalize datetime
        df['entry_date'] = pd.to_datetime(df['entry_date'], errors='coerce')
    except Exception:
        pass
    keys = df[['ticker','entry_date']].astype(str).agg('|'.join, axis=1)
    return int(keys.drop_duplicates().shape[0])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--month', required=True)
    ap.add_argument('--dir', default='reports/forecast')
    ap.add_argument('--out-json', default=None, help='Defaults to <dir>/<month>/activity_metrics.json')
    ap.add_argument('--update-kpi', action='store_true', help='Update kpi_all.json with unique_trades_executed and rows_all')
    args = ap.parse_args()

    mdir = Path(args.dir) / args.month
    all_csv = mdir / 'simulate_results_all.csv'
    if not all_csv.exists():
        print(f"[activity] No existe {all_csv}")
        return
    df = pd.read_csv(all_csv)
    rows_all = int(len(df))
    unique_trades = compute_unique_trades(df)
    out = {
        'month': args.month,
        'rows_all': rows_all,
        'unique_trades_executed': unique_trades,
    }

    if args.update_kpi:
        kpi_path = mdir / 'kpi_all.json'
        try:
            if kpi_path.exists():
                kpi = json.load(open(kpi_path, 'r', encoding='utf-8'))
            else:
                kpi = {}
            kpi['unique_trades_executed'] = unique_trades
            kpi['rows_all'] = rows_all
            json.dump(kpi, open(kpi_path, 'w', encoding='utf-8'), indent=2)
            print(f"[activity] kpi_all.json actualizado con unique_trades_executed={unique_trades}, rows_all={rows_all}")
        except Exception as e:
            print(f"[activity] Error actualizando kpi_all.json: {e}")

    out_json = Path(args.out_json) if args.out_json else (mdir / 'activity_metrics.json')
    try:
        json.dump(out, open(out_json, 'w', encoding='utf-8'), indent=2)
        print(f"[activity] Guardado -> {out_json}")
    except Exception as e:
        print(f"[activity] Error guardando {out_json}: {e}")

if __name__ == '__main__':
    main()
