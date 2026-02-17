# =============================================
# 19_build_ticker_universe.py
# =============================================
import argparse, os, pandas as pd

DEFAULT_CANDIDATES = [
    'data/us/tickers_tech.csv',
    'data/us/tickers_financials.csv',
    'data/us/tickers_energy.csv',
    'data/us/tickers_defensive.csv',
    'data/us/tickers_rotation.csv',
    'data/us/tickers_master.csv',
]

def read_tickers(path):
    try:
        if os.path.exists(path):
            df = pd.read_csv(path)
            if 'ticker' in df.columns:
                return df['ticker'].dropna().astype(str).tolist()
    except Exception:
        pass
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='data/us/tickers_expanded.csv')
    ap.add_argument('--max-count', type=int, default=20)
    ap.add_argument('--sources', default=','.join(DEFAULT_CANDIDATES), help='Lista separada por comas de CSVs con columna ticker')
    args = ap.parse_args()

    tickers = []
    for src in [s.strip() for s in args.sources.split(',') if s.strip()]:
        tks = read_tickers(src)
        for t in tks:
            if t not in tickers:
                tickers.append(t)
            if len(tickers) >= args.max_count:
                break
        if len(tickers) >= args.max_count:
            break

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    pd.DataFrame({'ticker': tickers}).to_csv(args.out, index=False)
    print(f"[universe] Construido {len(tickers)} tickers -> {args.out}")

if __name__ == '__main__':
    main()
