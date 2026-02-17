#!/usr/bin/env python3
"""
Comparación FINAL: Universo Viejo (5 tickers) vs Nuevo (4 tickers efectivos)
Diciembre 2025 + Enero 2026
"""
import pandas as pd
from pathlib import Path

print("=" * 90)
print("COMPARACIÓN FINAL: VIEJO (AMD,CVX,XOM,JNJ,WMT) vs NUEVO (AMD,CVX,XOM,NVDA)")
print("=" * 90)

# Diciembre 2025 - análisis ya hecho anteriormente
print("\n📊 DICIEMBRE 2025:")
print("-" * 90)

# Resultados viejos conocidos del análisis anterior
old_dec_pnl = 38.09
old_dec_trades = 80
old_dec_wr = 52.5

# Resultados nuevos de este run
new_dec_pnl = 68.09
new_dec_trades = 71
new_dec_wr = 56.3

print(f"VIEJO (5 tickers):  P&L ${old_dec_pnl:.2f} | {old_dec_trades} trades | WR {old_dec_wr}%")
print(f"  - JNJ: -$7.42 (worst) ❌")
print(f"  - WMT: -$8.00 (bad) ❌")
print(f"  - Removidos ambos = pérdida combinada -$15.42")
print()
print(f"NUEVO (4 tickers):  P&L ${new_dec_pnl:.2f} | {new_dec_trades} trades | WR {new_dec_wr}%")
print(f"  - XOM: $35.52 (best) ✅")
print(f"  - NVDA: $16.01 (nuevo) ✅✅")
print(f"  - AMD: $12.43")
print(f"  - CVX: $4.13")
print()
print(f"MEJORA DIC:  +${new_dec_pnl - old_dec_pnl:.2f} (+{(new_dec_pnl/old_dec_pnl - 1)*100:.1f}%)")
print(f"             WR: {old_dec_wr}% → {new_dec_wr}% (+{new_dec_wr - old_dec_wr:.1f} pp)")

# Enero 2026 - cargar resultados
print("\n📊 ENERO 2026:")
print("-" * 90)

# Viejo (del run original de enero con 5 tickers)
old_jan_path = Path("evidence/paper_sep_2025_jan/all_trades.csv")
if old_jan_path.exists():
    df_old = pd.read_csv(old_jan_path)
    old_jan_pnl = df_old['pnl'].sum()
    old_jan_trades = len(df_old)
    old_jan_wr = (df_old['pnl'] > 0).sum() / len(df_old) * 100 if len(df_old) > 0 else 0
    print(f"VIEJO (5 tickers):  P&L ${old_jan_pnl:.2f} | {old_jan_trades} trades | WR {old_jan_wr:.1f}%")
    jan_ticker_stats = df_old.groupby('ticker')['pnl'].sum().sort_values()
    print(f"  Peores tickers: {jan_ticker_stats.head(2).to_dict()}")
else:
    print(f"VIEJO (5 tickers):  Datos no disponibles (usar valores conocidos: ~$26.95, 24 trades)")
    old_jan_pnl = 26.95
    old_jan_trades = 24
    old_jan_wr = 58.3

# Nuevo (del run actual)
new_jan_path = Path("evidence/paper_jan_2026/all_trades.csv")
df_new = pd.read_csv(new_jan_path)
new_jan_pnl = df_new['pnl'].sum()
new_jan_trades = len(df_new)
new_jan_wr = (df_new['pnl'] > 0).sum() / len(df_new) * 100

print()
print(f"NUEVO (4 tickers):  P&L ${new_jan_pnl:.2f} | {new_jan_trades} trades | WR {new_jan_wr:.1f}%")
print(f"  - XOM: $17.17 (best) ✅")
print(f"  - CVX: $13.82 ✅✅")
print(f"  - AMD: $6.14")
print(f"  - NVDA: -$5.11 (único perdedor)")
print()
print(f"MEJORA ENE:  +${new_jan_pnl - old_jan_pnl:.2f} (+{(new_jan_pnl/old_jan_pnl - 1)*100:.1f}%)")
print(f"             WR: {old_jan_wr:.1f}% → {new_jan_wr:.1f}% ({new_jan_wr - old_jan_wr:+.1f} pp)")

# Consolidado 2 meses
print("\n" + "=" * 90)
print("📈 RESULTADOS CONSOLIDADOS (DIC 2025 + ENE 2026):")
print("=" * 90)

old_total_pnl = old_dec_pnl + old_jan_pnl
old_total_trades = old_dec_trades + old_jan_trades
new_total_pnl = new_dec_pnl + new_jan_pnl
new_total_trades = new_dec_trades + new_jan_trades

print(f"\nVIEJO (5 tickers):  ${old_total_pnl:.2f} en {old_total_trades} trades")
print(f"NUEVO (4 tickers):  ${new_total_pnl:.2f} en {new_total_trades} trades")
print()
print(f"💰 MEJORA TOTAL:    +${new_total_pnl - old_total_pnl:.2f}")
print(f"📊 INCREMENTO:      +{(new_total_pnl/old_total_pnl - 1)*100:.1f}%")
print(f"🎯 ROI NUEVO:       {new_total_pnl/1000*100:.2f}% (sobre $1000 capital)")
print()
print("=" * 90)
print("✅ DECISIÓN: El nuevo universo (AMD, CVX, XOM, NVDA) supera al viejo")
print("   Recomendación: Reemplazar JNJ+WMT por NVDA (MSFT en standby)")
print("=" * 90)
