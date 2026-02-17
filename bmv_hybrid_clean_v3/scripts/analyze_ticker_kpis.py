import pandas as pd
import sys

if len(sys.argv) < 2:
    print("Uso: python scripts/analyze_ticker_kpis.py <trades_csv>")
    sys.exit(1)

csv_path = sys.argv[1]
df = pd.read_csv(csv_path)

# Filtrar trades válidos
valid_trades = df[df['reason'] != 'NoBars']

# KPIs por ticker
kpi = valid_trades.groupby('ticker').agg(
    total_trades=('pnl','count'),
    win_trades=('pnl', lambda x: (x > 0).sum()),
    win_pct=('pnl', lambda x: 100*(x > 0).sum()/len(x)),
    total_pnl=('pnl','sum'),
    avg_pnl=('pnl','mean'),
    max_pnl=('pnl','max'),
    min_pnl=('pnl','min')
).sort_values('total_pnl')

print("KPIs por ticker:")
print(kpi)

# Sugerir tickers a eliminar si tienen pnl negativo o win_pct bajo
bad_tickers = kpi[(kpi['total_pnl'] < 0) | (kpi['win_pct'] < 30)].index.tolist()
if bad_tickers:
    print("\nTickers sugeridos para eliminar:", bad_tickers)
else:
    print("\nTodos los tickers tienen desempeño aceptable.")
