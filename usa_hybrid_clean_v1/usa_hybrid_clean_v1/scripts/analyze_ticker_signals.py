"""
Analiza qué tickers generaron señales en octubre
"""
import pandas as pd
from pathlib import Path
from collections import Counter

dates = [
    '2025-10-13','2025-10-14','2025-10-15','2025-10-16','2025-10-17',
    '2025-10-20','2025-10-21','2025-10-22','2025-10-23','2025-10-24',
    '2025-10-27','2025-10-30','2025-10-31'
]

ticker_counts = Counter()
date_ticker_map = {}

for d in dates:
    forecast_path = Path(f'reports/intraday/{d}/forecast_intraday.parquet')
    if forecast_path.exists():
        df = pd.read_parquet(forecast_path)
        if len(df) > 0:
            tickers = df['ticker'].unique().tolist()
            date_ticker_map[d] = tickers
            for t in tickers:
                ticker_counts[t] += 1
            print(f"{d}: {len(df)} señales de {tickers}")
        else:
            print(f"{d}: 0 señales")
    else:
        print(f"{d}: No existe forecast")

print("\n" + "="*80)
print("RESUMEN DE TICKERS")
print("="*80)
print(f"Tickers únicos que generaron señales: {len(ticker_counts)}")
print(f"Tickers: {list(ticker_counts.keys())}")
print("\nFrecuencia por ticker:")
for ticker, count in ticker_counts.most_common():
    print(f"  {ticker}: {count} días")

# Revisar whitelist
whitelist = ["AMD", "NVDA", "TSLA", "MSFT", "AAPL", "AMZN", "META", "GOOG", "NFLX", "JPM", "XOM"]
print(f"\n{'='*80}")
print(f"WHITELIST CONFIGURADA: {len(whitelist)} tickers")
print(f"{'='*80}")
for t in whitelist:
    if t in ticker_counts:
        print(f"  ✅ {t}: {ticker_counts[t]} días con señales")
    else:
        print(f"  ❌ {t}: 0 días con señales")
