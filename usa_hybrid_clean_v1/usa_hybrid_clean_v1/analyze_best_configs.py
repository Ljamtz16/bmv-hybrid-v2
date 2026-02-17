import json
import glob
from pathlib import Path

print("=" * 90)
print("🏆 ANÁLISIS DE MEJORES CONFIGURACIONES - PAPER TRADING")
print("=" * 90)

# Buscar todos los summary.json
paths = glob.glob('evidence/**/summary.json', recursive=True)

results = []
for p in paths:
    if 'paper' in p:
        try:
            with open(p, 'r') as f:
                data = json.load(f)
                config_name = Path(p).parent.name
                results.append({
                    'config': config_name,
                    'pnl': data.get('total_pnl', 0),
                    'win_rate': data.get('win_rate', 0),
                    'trades': data.get('total_trades', 0),
                    'final_equity': data.get('final_equity', 1000),
                    'avg_win': data.get('avg_win', 0),
                    'avg_loss': data.get('avg_loss', 0),
                    'mdd_pct': data.get('mdd_pct', 0),
                })
        except Exception as e:
            print(f"Error leyendo {p}: {e}")

# Ordenar por P&L
results_by_pnl = sorted(results, key=lambda x: x['pnl'], reverse=True)

print("\n🥇 TOP 10 CONFIGURACIONES POR P&L TOTAL")
print("=" * 90)
print(f"{'#':<3} {'Configuración':<50} {'P&L':>10} {'WR':>7} {'Trades':>7} {'Equity':>10}")
print("-" * 90)

for i, r in enumerate(results_by_pnl[:10], 1):
    print(f"{i:<3} {r['config']:<50} ${r['pnl']:>9.2f} {r['win_rate']:>6.1f}% {r['trades']:>7} ${r['final_equity']:>9.2f}")

# Ordenar por win rate
results_by_wr = sorted(results, key=lambda x: x['win_rate'], reverse=True)

print("\n\n🎯 TOP 10 CONFIGURACIONES POR WIN RATE")
print("=" * 90)
print(f"{'#':<3} {'Configuración':<50} {'WR':>7} {'P&L':>10} {'Trades':>7}")
print("-" * 90)

for i, r in enumerate(results_by_wr[:10], 1):
    if r['trades'] >= 10:  # Solo configs con volumen significativo
        print(f"{i:<3} {r['config']:<50} {r['win_rate']:>6.1f}% ${r['pnl']:>9.2f} {r['trades']:>7}")

# Ordenar por Sharpe-like (retorno/riesgo)
results_with_sharpe = []
for r in results:
    if r['trades'] >= 10 and r['mdd_pct'] > 0:
        sharpe_like = r['pnl'] / r['mdd_pct']
        r['sharpe_like'] = sharpe_like
        results_with_sharpe.append(r)

results_by_sharpe = sorted(results_with_sharpe, key=lambda x: x['sharpe_like'], reverse=True)

print("\n\n⚖️ TOP 10 CONFIGURACIONES POR RETORNO/RIESGO (P&L/MDD)")
print("=" * 90)
print(f"{'#':<3} {'Configuración':<50} {'Ratio':>8} {'P&L':>10} {'MDD':>7}")
print("-" * 90)

for i, r in enumerate(results_by_sharpe[:10], 1):
    print(f"{i:<3} {r['config']:<50} {r['sharpe_like']:>8.2f} ${r['pnl']:>9.2f} {r['mdd_pct']:>6.1f}%")

# Mejor balance: WR > 60%, trades >= 20, P&L positivo
print("\n\n💎 CONFIGURACIONES BALANCEADAS (WR>60%, Trades>=20, P&L>0)")
print("=" * 90)
print(f"{'Configuración':<50} {'P&L':>10} {'WR':>7} {'Trades':>7} {'MDD':>7}")
print("-" * 90)

balanced = [r for r in results if r['win_rate'] > 60 and r['trades'] >= 20 and r['pnl'] > 0]
balanced = sorted(balanced, key=lambda x: x['pnl'], reverse=True)

if balanced:
    for r in balanced[:10]:
        print(f"{r['config']:<50} ${r['pnl']:>9.2f} {r['win_rate']:>6.1f}% {r['trades']:>7} {r['mdd_pct']:>6.1f}%")
else:
    print("No se encontraron configuraciones que cumplan todos los criterios")

print("\n" + "=" * 90)
print(f"\n✅ Total configuraciones analizadas: {len(results)}")
print(f"✅ Configuraciones rentables (P&L > 0): {len([r for r in results if r['pnl'] > 0])}")
print(f"✅ Configuraciones con WR > 60%: {len([r for r in results if r['win_rate'] > 60])}")
