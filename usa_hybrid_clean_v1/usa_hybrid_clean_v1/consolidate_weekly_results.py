"""
Consolidar todos los archivos generados por el backtest semanal en archivos únicos
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# Directorios
weekly_dir = Path('evidence/weekly_analysis')
output_dir = weekly_dir / 'consolidated'
output_dir.mkdir(exist_ok=True)

# ==============================================================================
# 1. CONSOLIDAR TODOS LOS TRADES EN UN CSV ÚNICO
# ==============================================================================
print("=" * 100)
print("CONSOLIDANDO TRADES DE TODAS LAS SEMANAS")
print("=" * 100)

all_trades = []
week_folders = sorted([f for f in weekly_dir.iterdir() if f.is_dir() and f.name[0].isdigit()])

for week_folder in week_folders:
    trades_file = week_folder / 'trades.csv'
    if trades_file.exists():
        df = pd.read_csv(trades_file)
        df['week'] = week_folder.name
        all_trades.append(df)
        print(f"✅ {week_folder.name}: {len(df)} trades")
    else:
        print(f"⚠️  {week_folder.name}: no trades.csv")

if all_trades:
    consolidated_trades = pd.concat(all_trades, ignore_index=True)
    output_trades = output_dir / 'ALL_TRADES_2024_2025.csv'
    consolidated_trades.to_csv(output_trades, index=False)
    print(f"\n✅ Archivo consolidado: {output_trades}")
    print(f"   Total trades: {len(consolidated_trades)}")
    print(f"   Columnas: {list(consolidated_trades.columns)}")

# ==============================================================================
# 2. CONSOLIDAR TODOS LOS METRICS EN UN JSON ÚNICO
# ==============================================================================
print("\n" + "=" * 100)
print("CONSOLIDANDO METRICS DE TODAS LAS SEMANAS")
print("=" * 100)

all_metrics = {}
for week_folder in week_folders:
    metrics_file = week_folder / 'metrics.json'
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics = json.load(f)
        all_metrics[week_folder.name] = metrics
        print(f"✅ {week_folder.name}: {metrics.get('n_trades', 0)} trades, {metrics.get('return_pct', 0):.2f}% return")
    else:
        print(f"⚠️  {week_folder.name}: no metrics.json")

if all_metrics:
    output_metrics = output_dir / 'ALL_METRICS_2024_2025.json'
    with open(output_metrics, 'w') as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\n✅ Archivo consolidado: {output_metrics}")
    print(f"   Total weeks: {len(all_metrics)}")

# ==============================================================================
# 3. CREAR DATAFRAME CONSOLIDADO DE MÉTRICAS POR SEMANA
# ==============================================================================
print("\n" + "=" * 100)
print("GENERANDO TABLA CONSOLIDADA DE MÉTRICAS")
print("=" * 100)

metrics_rows = []
for week_name, metrics in all_metrics.items():
    row = {
        'week': week_name,
        'return_pct': metrics.get('return_pct', 0),
        'total_pnl': metrics.get('total_pnl', 0),
        'n_trades': metrics.get('n_trades', 0),
        'win_rate': metrics.get('win_rate', 0),
        'profit_factor': metrics.get('profit_factor', 0),
        'avg_pnl_per_trade': metrics.get('avg_pnl_per_trade', 0),
        'final_equity': metrics.get('final_equity', 0),
        'max_drawdown_pct': metrics.get('max_drawdown_pct', 0),
        'sharpe_ratio': metrics.get('sharpe_ratio', 0),
        'sortino_ratio': metrics.get('sortino_ratio', 0),
    }
    metrics_rows.append(row)

metrics_df = pd.DataFrame(metrics_rows)
output_metrics_csv = output_dir / 'METRICS_TABLE_2024_2025.csv'
metrics_df.to_csv(output_metrics_csv, index=False)

print(f"✅ Tabla de métricas: {output_metrics_csv}")
print(f"   Filas: {len(metrics_df)}")
print(f"   Columnas: {list(metrics_df.columns)}\n")

# Mostrar resumen
print("\n" + "=" * 100)
print("RESUMEN FINAL")
print("=" * 100)

print(f"\nTotal semanas:          {len(all_metrics)}")
print(f"Total trades:           {len(consolidated_trades)}")
print(f"\nReturn promedio:        {metrics_df['return_pct'].mean():+.2f}%")
print(f"Return total (sum):     {metrics_df['return_pct'].sum():+.2f}%")
print(f"Return min:             {metrics_df['return_pct'].min():+.2f}%")
print(f"Return max:             {metrics_df['return_pct'].max():+.2f}%")
print(f"Return std dev:         {metrics_df['return_pct'].std():.2f}%")

print(f"\nSemanas positivas:      {(metrics_df['return_pct'] > 0).sum()} / {len(metrics_df)}")
print(f"Semanas negativas:      {(metrics_df['return_pct'] < 0).sum()} / {len(metrics_df)}")
print(f"Semanas sin trades:     {(metrics_df['n_trades'] == 0).sum()} / {len(metrics_df)}")

print(f"\nWin rate promedio:      {metrics_df['win_rate'].mean():.1%}")
print(f"Profit factor promedio: {metrics_df['profit_factor'].mean():.2f}x")

print(f"\n✅ Archivos consolidados guardados en:")
print(f"   {output_dir.relative_to(Path.cwd())}/")
print(f"\n   • ALL_TRADES_2024_2025.csv (todas las operaciones)")
print(f"   • ALL_METRICS_2024_2025.json (métricas por semana)")
print(f"   • METRICS_TABLE_2024_2025.csv (tabla resumida)")
print(f"   • weekly_summary.csv (ya existía)")
print(f"   • weekly_summary.json (ya existía)")

print("\n" + "=" * 100)
