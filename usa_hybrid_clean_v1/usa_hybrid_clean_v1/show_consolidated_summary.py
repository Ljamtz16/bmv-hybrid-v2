import pandas as pd
import json

print("="*100)
print("RESUMEN DE ARCHIVOS CONSOLIDADOS")
print("="*100)

# Trades
trades_df = pd.read_csv('evidence/weekly_analysis/consolidated/ALL_TRADES_2024_2025.csv')
print(f"\n📊 ALL_TRADES_2024_2025.csv")
print(f"   Total trades: {len(trades_df)}")
print(f"   Columnas: {list(trades_df.columns)}")
print(f"   Profit trades: {(trades_df['pnl'] > 0).sum()}")
print(f"   Loss trades: {(trades_df['pnl'] < 0).sum()}")
print(f"   Total PnL: ${trades_df['pnl'].sum():+.2f}")
print(f"\n   Primeras 5 operaciones:")
print(trades_df[['week', 'ticker', 'entry_date', 'exit_date', 'pnl', 'pnl_pct']].head().to_string(index=False))

# Metrics Table
metrics_df = pd.read_csv('evidence/weekly_analysis/consolidated/METRICS_TABLE_2024_2025.csv')
print(f"\n\n📊 METRICS_TABLE_2024_2025.csv")
print(f"   Total semanas: {len(metrics_df)}")
print(f"   Columnas: {list(metrics_df.columns)}")
print(f"\n   Primeras 5 semanas:")
print(metrics_df[['week', 'return_pct', 'n_trades', 'win_rate', 'total_pnl']].head().to_string(index=False))

# All Metrics JSON
with open('evidence/weekly_analysis/consolidated/ALL_METRICS_2024_2025.json') as f:
    all_metrics = json.load(f)
print(f"\n\n📊 ALL_METRICS_2024_2025.json")
print(f"   Total semanas: {len(all_metrics)}")
print(f"   Estructura: Diccionario con semana como llave")
print(f"   Primeras 2 semanas:")
for i, (week, metrics) in enumerate(list(all_metrics.items())[:2]):
    ret = metrics.get("return_pct", 0)
    trades = metrics.get("n_trades", 0)
    wr = metrics.get("win_rate", 0)
    print(f"     {week}: return={ret:.2f}%, trades={trades}, WR={wr:.1%}")

print("\n" + "="*100)
print("UBICACIÓN DE ARCHIVOS:")
print("="*100)
print("\n✅ evidence/weekly_analysis/consolidated/")
print("   ├── ALL_TRADES_2024_2025.csv        (1,127 operaciones consolidadas)")
print("   ├── METRICS_TABLE_2024_2025.csv     (105 semanas resumidas)")
print("   └── ALL_METRICS_2024_2025.json      (105 semanas con detalle completo)")
print("\nAdemás ya existían:")
print("   ├── weekly_summary.csv")
print("   └── weekly_summary.json")
print("\n" + "="*100)
