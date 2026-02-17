# =============================================
# 31_merge_trades_intraday.py
# =============================================
# Une trades_detailed.csv con intraday_validation.csv por (ticker, entry_date)
# y escribe trades_detailed_enriched.csv con flags de TP/SL intradía.

import argparse, os
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--dir", default="reports/forecast")
    ap.add_argument("--trades-file", default="trades_detailed.csv")
    ap.add_argument("--intraday-file", default="intraday_validation.csv")
    ap.add_argument("--out-file", default="trades_detailed_enriched.csv")
    args = ap.parse_args()

    base = os.path.join(args.dir, args.month)
    tpath = os.path.join(base, args.trades_file)
    ipath = os.path.join(base, args.intraday_file)
    if not os.path.exists(tpath) or not os.path.exists(ipath):
        raise SystemExit(f"Faltan archivos para merge: {tpath} | {ipath}")

    td = pd.read_csv(tpath)
    iv = pd.read_csv(ipath)

    # Normalizar columnas
    td.columns = [c.strip().lower() for c in td.columns]
    iv.columns = [c.strip().lower() for c in iv.columns]

    # Asegurar entry_date comparable (td usa entry_dt)
    if 'entry_dt' in td.columns:
        td['entry_date'] = pd.to_datetime(td['entry_dt']).dt.date.astype(str)
    elif 'entry_date' in td.columns:
        td['entry_date'] = pd.to_datetime(td['entry_date']).dt.date.astype(str)
    else:
        td['entry_date'] = ''

    if 'entry_date' in iv.columns:
        iv['entry_date'] = pd.to_datetime(iv['entry_date']).astype(str)

    keys = ['ticker','entry_date']
    merged = td.merge(iv, on=keys, how='left', suffixes=('','_intraday'))

    # Ordenar columnas clave al frente
    front = [c for c in ['ticker','sector','entry_dt','exit_dt','entry_price','exit_price','shares','cash_used','pnl','rr','close_reason','tp_price','sl_price','tp_hit_intraday','sl_hit_intraday','tp_ts','sl_ts'] if c in merged.columns]
    rest = [c for c in merged.columns if c not in front]
    out = merged[front + rest]

    out_path = os.path.join(base, args.out_file)
    out.to_csv(out_path, index=False)
    print(f"[merge-intraday] Guardado -> {out_path} (rows={len(out)})")


if __name__ == "__main__":
    main()
