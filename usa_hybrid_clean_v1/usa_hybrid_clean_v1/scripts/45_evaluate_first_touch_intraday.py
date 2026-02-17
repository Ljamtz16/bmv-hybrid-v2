import pandas as pd
import os
import glob

HISTORY_5M = "data/intraday5/history/"
HISTORY_15M = "data/intraday15/history/"
PREDICTIONS_LOG = "data/trading/predictions_log.csv"


def find_first_touch(df, entry, tp, sl, side):
    for i, row in df.iterrows():
        price = row['high'] if side == 'BUY' else row['low']
        if side == 'BUY':
            if price >= tp:
                return 'TP', row['timestamp']
            if row['low'] <= sl:
                return 'SL', row['timestamp']
        else:
            if price <= tp:
                return 'TP', row['timestamp']
            if row['high'] >= sl:
                return 'SL', row['timestamp']
    return 'NONE', None

def evaluate_first_touch():
    if not os.path.exists(PREDICTIONS_LOG):
        print(f"[WARN] No existe {PREDICTIONS_LOG}")
        return
    df_pred = pd.read_csv(PREDICTIONS_LOG)
    outcomes = []
    for idx, row in df_pred.iterrows():
        ticker = row['ticker']
        date = row['date']
        entry = row['entry']
        tp = row['tp']
        sl = row['sl']
        side = row.get('side', 'BUY')
        # Buscar datos 5m
        fglob = f"{HISTORY_5M}ticker={ticker}/date={date}/*.parquet"
        files = glob.glob(fglob)
        df_5m = pd.concat([pd.read_parquet(f) for f in files]) if files else pd.DataFrame()
        if not df_5m.empty:
            outcome, ts = find_first_touch(df_5m, entry, tp, sl, side)
        else:
            # Fallback 15m
            fglob = f"{HISTORY_15M}ticker={ticker}/date={date}/*.parquet"
            files = glob.glob(fglob)
            df_15m = pd.concat([pd.read_parquet(f) for f in files]) if files else pd.DataFrame()
            outcome, ts = find_first_touch(df_15m, entry, tp, sl, side) if not df_15m.empty else ('NONE', None)
        outcomes.append({'outcome': outcome, 'hit_timestamp': ts})
    df_pred['outcome'] = [o['outcome'] for o in outcomes]
    df_pred['hit_timestamp'] = [o['hit_timestamp'] for o in outcomes]
    df_pred.to_csv(PREDICTIONS_LOG, index=False)
    print(f"[OK] Evaluación first-touch completada y guardada en {PREDICTIONS_LOG}")

if __name__ == "__main__":
    evaluate_first_touch()
