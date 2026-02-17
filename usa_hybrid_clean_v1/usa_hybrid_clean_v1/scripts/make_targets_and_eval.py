# =============================================
# 2. make_targets_and_eval.py
# =============================================
import pandas as pd, numpy as np, argparse, os

def add_features(df):
    df = df.sort_values(['ticker','date']).copy()
    # Retorno 1 día sin forward fill implícito
    df['ret1'] = df.groupby('ticker', group_keys=False)['close'].pct_change(fill_method=None)

    # Medias exponenciales
    df['ema10'] = df.groupby('ticker', group_keys=False)['close'].transform(lambda x: x.ewm(span=10, adjust=False).mean())
    df['ema20'] = df.groupby('ticker', group_keys=False)['close'].transform(lambda x: x.ewm(span=20, adjust=False).mean())

    # RSI 14 simple
    def _rsi(series, n=14):
        delta = series.diff()
        up = delta.clip(lower=0).rolling(n, min_periods=1).mean()
        down = (-delta.clip(upper=0)).rolling(n, min_periods=1).mean()
        rs = up / (down.replace(0, pd.NA))
        return 100 - 100/(1 + rs)
    df['rsi14'] = df.groupby('ticker', group_keys=False)['close'].transform(lambda s: _rsi(s, 14))

    # ATR 14 sin groupby.apply para evitar warnings
    def _atr(g):
        high, low, close = g['high'], g['low'], g['close']
        tr = pd.concat([
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(14, min_periods=1).mean()
    df['atr14'] = df.groupby('ticker', group_keys=False).apply(lambda g: _atr(g)).reset_index(level=0, drop=True)
    df['atr_pct'] = df['atr14']/df['close']

    # Z-score de volumen
    df['vol_z'] = df.groupby('ticker', group_keys=False)['volume'].transform(lambda x: (x - x.rolling(20, min_periods=1).mean()) / x.rolling(20, min_periods=1).std())
    return df

def add_targets(df, horizon=3):
    df = df.copy()
    df['y_H3'] = df.groupby('ticker')['close'].shift(-horizon)/df['close'] - 1
    df['y_H5'] = df.groupby('ticker')['close'].shift(-5)/df['close'] - 1
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/us/ohlcv_us_daily.csv")
    ap.add_argument("--out", default="features_labeled.csv")
    args = ap.parse_args()
    # Solo crear directorio si el path incluye un directorio
    if os.path.dirname(args.out):
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df = pd.read_csv(args.input)
    df['date'] = pd.to_datetime(df['date'])
    df = add_features(df)
    df = add_targets(df)
    df.to_csv(args.out, index=False)
    print(f"[features] Guardado {args.out} ({len(df)} filas)")

if __name__ == "__main__":
    main()
