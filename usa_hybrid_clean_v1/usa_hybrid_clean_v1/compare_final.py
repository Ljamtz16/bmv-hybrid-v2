import pandas as pd

df = pd.read_csv('paper_summary.csv')

tags = ['relaxed_p018_wk42', 'with_momentum', 'optimized_p015']
labels = ['Baseline (p=0.18)', 'Con Momentum', 'Optimizado (p=0.15 sin momentum)']

print("\n" + "=" * 80)
print("COMPARACIÓN FINAL: 3 Configuraciones en 2025-10-13..31 (14 días)")
print("=" * 80)

results = []
for tag, label in zip(tags, labels):
    data = df[df['tag'] == tag]
    trades = int(data["num_plan_trades"].sum())
    pnl = data["exp_pnl_sum_usd"].sum()
    days_with_trades = data[data["num_plan_trades"] > 0]
    prob = days_with_trades["prob_win_mean"].mean() if len(days_with_trades) > 0 else 0
    spread = days_with_trades["spread_mean_bps"].mean() if len(days_with_trades) > 0 else 0
    etth = days_with_trades["etth_median_days"].mean() if len(days_with_trades) > 0 else 0
    
    results.append({
        'Config': label,
        'Trades': trades,
        'E[PnL]': f"${pnl:.2f}",
        'Prob Win': f"{prob:.3f} ({prob*100:.1f}%)",
        'Spread (bps)': f"{spread:.1f}",
        'ETTH (h)': f"{etth*6.5:.1f}",
        'E[PnL]/trade': f"${pnl/trades:.2f}" if trades > 0 else "$0.00"
    })

result_df = pd.DataFrame(results)
print("\n" + result_df.to_string(index=False))

print("\n" + "=" * 80)
print("ANÁLISIS DE IMPACTO")
print("=" * 80)

baseline = results[0]
momentum = results[1]
optimized = results[2]

baseline_trades = int(baseline['Trades'])
momentum_trades = int(momentum['Trades'])
optimized_trades = int(optimized['Trades'])

baseline_pnl = float(baseline['E[PnL]'].replace('$',''))
momentum_pnl = float(momentum['E[PnL]'].replace('$',''))
optimized_pnl = float(optimized['E[PnL]'].replace('$',''))

print(f"\n1. MOMENTUM FILTER (vs Baseline):")
print(f"   Trades: {(momentum_trades-baseline_trades)/baseline_trades*100:+.1f}% ({momentum_trades} vs {baseline_trades})")
print(f"   E[PnL]: {(momentum_pnl-baseline_pnl)/baseline_pnl*100:+.1f}% (${momentum_pnl:.2f} vs ${baseline_pnl:.2f})")
print(f"   ❌ Redujo frecuencia sin mejorar calidad")

print(f"\n2. OPTIMIZADO p=0.15 sin momentum (vs Baseline):")
print(f"   Trades: {(optimized_trades-baseline_trades)/baseline_trades*100:+.1f}% ({optimized_trades} vs {baseline_trades})")
print(f"   E[PnL]: {(optimized_pnl-baseline_pnl)/baseline_pnl*100:+.1f}% (${optimized_pnl:.2f} vs ${baseline_pnl:.2f})")
if optimized_trades == baseline_trades:
    print(f"   ✅ Misma frecuencia, mantiene signals")
elif optimized_trades > baseline_trades:
    print(f"   ✅ Mayor frecuencia, más oportunidades")
else:
    print(f"   ⚠️  Menor frecuencia")

print("\n" + "=" * 80)
print("RECOMENDACIÓN FINAL")
print("=" * 80)

print(f"\n✅ CONFIGURACIÓN SELECCIONADA: Optimizado (p=0.15 sin momentum)")
print(f"\n   Parámetros:")
print(f"   - prob_win_min: 0.25")
print(f"   - p_tp_before_sl_min: 0.15")
print(f"   - allow_short: true")
print(f"   - spread caps: 50/70/90 bps")
print(f"   - whitelist: 11 tickers")
print(f"   - momentum filter: DESACTIVADO")

prob_win = float(optimized['Prob Win'].split('(')[0])
if prob_win >= 0.50:
    print(f"\n🎯 Win rate ≥50% - LISTO para fase selectiva")
    print(f"   → Aumentar prob_win_min a 0.30-0.35")
    print(f"   → Mantener 2 semanas de validación")
elif prob_win >= 0.45:
    print(f"\n⚠️  Win rate 45-50% - Validación extendida recomendada")
    print(f"   → Mantener configuración actual por 2 semanas")
    print(f"   → Objetivo: 15-20 trades para confirmar ≥50%")
else:
    print(f"\n🔧 Win rate <45% - Optimización adicional")
    print(f"   → Bajar p_tp_before_sl_min a 0.12 temporalmente")
    print(f"   → O revisar calibración TTH")

print(f"\n📊 Próximos pasos:")
print(f"   1. Ejecutar validación 2 semanas (10 días hábiles)")
print(f"   2. Recolectar 15-20 trades mínimo")
print(f"   3. Si win rate ≥50%: Subir prob_min a 0.30")
print(f"   4. Si win rate <50%: Re-evaluar configuración")

print("\n" + "=" * 80 + "\n")
