# =============================================
# 20_detect_patterns.py
# =============================================
import argparse, os, pandas as pd, numpy as np

def atr(df, n=14):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=1).mean()

def zigzag(df, pct=0.05):
    df = df.copy(); df['zz'] = np.nan
    last_pivot = df['close'].iloc[0]; direction = 0
    for i in range(1,len(df)):
        chg = (df['close'].iloc[i]-last_pivot)/last_pivot
        if direction>=0 and chg<=-pct: direction=-1; last_pivot=df['close'].iloc[i]; df.loc[df.index[i],'zz']=last_pivot
        elif direction<=0 and chg>=pct: direction=1; last_pivot=df['close'].iloc[i]; df.loc[df.index[i],'zz']=last_pivot
    return df

def detect_patterns(df, zz_pct=0.05):
    zz = zigzag(df, zz_pct)
    pat = pd.DataFrame(index=df.index)
    pat['double_top'] = ((zz['zz'].notna()) & (df['close']>df['close'].shift(5))).astype(int)
    pat['double_bottom'] = ((zz['zz'].notna()) & (df['close']<df['close'].shift(5))).astype(int)
    return pat

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/us/ohlcv_us_daily.csv")
    ap.add_argument("--outdir", default="reports/patterns")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    df = pd.read_csv(args.input)
    df['date'] = pd.to_datetime(df['date'])
    results=[]
    for tkr,g in df.groupby('ticker'):
        p=detect_patterns(g)
        out=g[['date','ticker']].join(p)
        out.to_csv(os.path.join(args.outdir,f"{tkr}.csv"),index=False)
        results.append(out)
    print(f"[patterns] Generados {len(results)} archivos en {args.outdir}")

if __name__=="__main__":
    main()