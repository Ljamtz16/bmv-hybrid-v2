"""
═══════════════════════════════════════════════════════════════════════════════
🚀 INTRADAY 2.0 - REPORTE DE IMPLEMENTACIÓN
═══════════════════════════════════════════════════════════════════════════════

📅 Fecha implementación: Noviembre 4, 2025
🎯 Objetivo: 1-2 trades/día con E[PnL] $1-3/día en paper
💰 Capital: $900 máx, $300/trade
📊 Parámetros: TP=1.2%, SL=0.35%, R:R=3.4:1, cost=0.05%

═══════════════════════════════════════════════════════════════════════════════
✅ CAMBIOS IMPLEMENTADOS
═══════════════════════════════════════════════════════════════════════════════

1. CONFIGURACIÓN ACTUALIZADA (config/intraday.yaml):

   filters:
     prob_win_min: 0.08         # 8% (vs 3% anterior)
     p_tp_before_sl_min: 0.15   # 15% (mantener)
     etth_max_days: 0.28        # ~6.7 barras máximo
     atr15m_min: 0.0035         # 0.35% (evita días planos)
     spread_bps: 50/70/90       # Caps conservadores

   risk:
     tp_pct: 0.012              # 1.2% (vs 2.0% anterior)
     sl_pct: 0.0035             # 0.35% (vs 0.4% anterior)
     cost_pct: 0.0005           # 0.05% (50 bps round-trip)

   capital:
     max_total: 900             # $900 (vs $2,000 anterior)
     per_trade_cash: 300        # $300 (vs $500 anterior)
     max_open: 2                # 2 simultáneos máximo

   tth:
     scale_tp: 1.00             # Calibración TP
     scale_sl: 1.00             # Calibración SL

2. R:R MEJORADO:
   • Anterior: TP=2.0% / SL=0.4% = R:R 5:1
   • Nuevo: TP=1.2% / SL=0.35% = R:R 3.4:1
   • Trade-off: Menor R:R pero MAYOR hit rate esperado

3. CAPITAL SIZING:
   • Anterior: $500/trade → pérdidas de -$1.60 a -$2.50
   • Nuevo: $300/trade → pérdidas controladas -$0.70 a -$1.05
   • Lógica: Más frecuencia + menor riesgo

═══════════════════════════════════════════════════════════════════════════════
📊 VALIDACIÓN OCT 28, 2025
═══════════════════════════════════════════════════════════════════════════════

SEÑALES GENERADAS:
   • prob_win ≥ 8%: 11 candidatos (vs 20 con 3%)
   • After filters: 2 señales
   • Ticker: NVDA únicamente

TTH PREDICTION:
   • P(TP<SL) media: 33.6% ✅ (vs 25% en Profit Mode)
   • ETTH media: 0.11d (2.8h)
   • Mejora significativa en probabilidad de éxito

PLAN GENERADO:
   • Trades: 1 (objetivo 1-2 ✅)
   • Ticker: NVDA LONG @ $199.99
   • TP: $202.38 (+1.2%), SL: $199.29 (-0.35%)
   • Exposure: $199.99
   • Prob win: 30.6%, P(TP<SL): 35.2%
   • E[PnL]: $0.29

RESULTADO REAL:
   ❌ SL HIT after 15 min
   PnL: -$0.70 (-0.35%)

COMPARACIÓN:
┌─────────────────┬──────────────┬──────────────┬───────────┐
│ Config          │ TP / SL      │ Resultado    │ PnL       │
├─────────────────┼──────────────┼──────────────┼───────────┤
│ Profit Mode     │ 2.0% / 0.4%  │ SL hit 15min │ -$1.60    │
│ Intraday 2.0    │ 1.2% / 0.35% │ SL hit 15min │ -$0.70    │
│ MEJORA          │ -            │ -            │ +$0.90 ✅ │
└─────────────────┴──────────────┴──────────────┴───────────┘

💡 Pérdida reducida 56% con nuevo config

═══════════════════════════════════════════════════════════════════════════════
📈 MEJORAS CLAVE vs VERSIONES ANTERIORES
═══════════════════════════════════════════════════════════════════════════════

1. ✅ P(TP<SL) MÁS ALTA:
   • Anterior: 25-28%
   • Nuevo: 33-35%
   • Impacto: +30% mejor ratio

2. ✅ PÉRDIDAS CONTROLADAS:
   • Anterior: -$1.60 por SL hit
   • Nuevo: -$0.70 por SL hit
   • Impacto: -56% en pérdidas

3. ✅ TP MÁS REALISTA:
   • Anterior TP=2.0%: 0% hit rate en 6 trades
   • Nuevo TP=1.2%: Hit rate esperado 30-35%

4. ✅ FILTROS OPTIMIZADOS:
   • prob_win ≥ 8%: Embudo más selectivo
   • ATR ≥ 0.35%: Evita días planos
   • P(TP<SL) ≥ 15%: Mínimo probabilístico

5. ✅ CAPITAL EFICIENTE:
   • $300/trade: Permite 2-3 trades simultáneos
   • Max exposure $900: Control de riesgo

═══════════════════════════════════════════════════════════════════════════════
⚠️ LIMITACIONES IDENTIFICADAS
═══════════════════════════════════════════════════════════════════════════════

1. 🟡 FRECUENCIA BAJA EN DÍAS ESPECÍFICOS:
   • Oct 28: Solo 1 trade generado (objetivo 2)
   • Causa: Filtro spread eliminó 6 de 9 candidatos
   • Solución: Considerar relajar spread a 60/80/100 si persiste

2. 🟡 TIMING TARDÍO PERSISTE:
   • Oct 28 NVDA: Entrada 14:45, solo 1h15min hasta cierre
   • Problema: Poco tiempo para desarrollar movimiento
   • SOLUCIÓN PENDIENTE: Filtrar señales >13:00

3. 🟡 SL SIGUE SIENDO TIGHT:
   • SL=0.35% hit en primer bar (15 min)
   • Volatilidad normal puede activar SL prematuramente
   • Considerar: SL=0.4-0.5% o ATR-based dynamic

4. 🟡 UN SOLO TICKER EN PLAN:
   • Solo NVDA pasó filtros en Oct 28
   • Falta diversificación (objetivo: 2-3 tickers)
   • Revisar: whitelist, volume_ratio calculation

═══════════════════════════════════════════════════════════════════════════════
🎯 PRÓXIMOS PASOS (Prioridad)
═══════════════════════════════════════════════════════════════════════════════

🔥 PRIORIDAD CRÍTICA:

1. IMPLEMENTAR FILTRO DE TIMING:
   ```python
   # En script 11 o como filtro adicional
   df = df[df['timestamp'].dt.hour < 13]  # Rechazar entradas >13:00
   ```

2. RE-ENTRENAR MODELO CON TP=1.2%, SL=0.35%:
   ```powershell
   python scripts\09_make_targets_and_eval_intraday.py \
     --start 2025-09-01 --end 2025-10-31 \
     --tp-pct 0.012 --sl-pct 0.0035 --bars 26
   
   python scripts\10_train_intraday_brf.py \
     --start 2025-09-01 --end 2025-10-31 \
     --features-dir features\intraday \
     --models-dir models --use-smote
   ```

3. CALCULAR VOLUME_RATIO REAL:
   • Leer CSV intraday históricos
   • Calcular volume_20d_ma
   • Agregar a features antes de filtrar

📊 PRIORIDAD MEDIA:

4. VALIDAR MÚLTIPLES FECHAS OCTUBRE:
   ```powershell
   $dates = @('2025-10-21','2025-10-22','2025-10-23','2025-10-24','2025-10-27','2025-10-28','2025-10-29','2025-10-30')
   foreach ($d in $dates) {
     python scripts\11_infer_and_gate_intraday.py --date $d --prob-min 0.08
     python scripts\39_predict_tth_intraday.py --date $d
     python scripts\40_make_trade_plan_intraday.py --date $d --tp-pct 0.012 --sl-pct 0.0035 --per-trade-cash 300 --capital-max 900
   }
   ```

5. SWEEP TP CON MODELO RE-ENTRENADO:
   • Probar TP: 1.0%, 1.2%, 1.5%, 1.8%
   • Medir hit rates reales vs predichos
   • Seleccionar óptimo balance hit-rate / reward

6. AJUSTAR SL SI NECESARIO:
   • Si hit rate TP<20% con 1.2%, considerar TP=1.5%
   • Si SL hits >60%, considerar SL=0.4-0.5%
   • Trade-off: R:R vs win-rate

═══════════════════════════════════════════════════════════════════════════════
💰 EXPECTATIVA REALISTA POST RE-ENTRENAMIENTO
═══════════════════════════════════════════════════════════════════════════════

Con modelo re-entrenado (TP=1.2%, SL=0.35%) + timing fix (<13:00):

FRECUENCIA:
   • 1-2 trades/día en días volátiles (5-10 días/mes)
   • 0 trades en días planos (<15 días/mes)
   • Promedio: 10-15 trades/mes

WIN RATE ESPERADO:
   • TP hits: 30-35% (vs 0% actual)
   • SL hits: 40-50%
   • EOD closes: 15-20%

PNL POR TRADE:
   • Ganador (TP): +$3.60 (+1.2% de $300)
   • Perdedor (SL): -$1.05 (-0.35% de $300)
   • EOD neutral: -$0.15 a +$0.30

PNL ESPERADO:
   Por día (2 trades):
     • Mejor caso (2 TP): +$7.20
     • Caso medio (1 TP, 1 SL): +$2.55
     • Peor caso (2 SL): -$2.10
   
   Por mes (12 trades, 35% win-rate):
     • 4 ganadores: +$14.40
     • 8 perdedores: -$8.40
     • Total: +$6.00/mes
   
   Con 20 trades/mes (40% win-rate):
     • 8 ganadores: +$28.80
     • 12 perdedores: -$12.60
     • Total: +$16.20/mes

═══════════════════════════════════════════════════════════════════════════════
📝 COMANDOS PARA EJECUTAR HOY
═══════════════════════════════════════════════════════════════════════════════

# 1. Re-etiquetar con nuevos parámetros (si existe script)
python scripts\09_make_targets_and_eval_intraday.py --start 2025-09-01 --end 2025-10-31 --tp-pct 0.012 --sl-pct 0.0035 --bars 26

# 2. Re-entrenar modelo (si existe script)
python scripts\10_train_intraday_brf.py --start 2025-09-01 --end 2025-10-31 --features-dir features\intraday --models-dir models --use-smote

# 3. Validar pipeline completo Oct 28
python scripts\11_infer_and_gate_intraday.py --date 2025-10-28 --prob-min 0.08
python scripts\39_predict_tth_intraday.py --date 2025-10-28
python scripts\40_make_trade_plan_intraday.py --date 2025-10-28 --tp-pct 0.012 --sl-pct 0.0035 --per-trade-cash 300 --capital-max 900

# 4. Validar contra datos reales
python scripts\validate_intraday_2_0.py

# 5. Si plan vacío, usar ensure-one
python scripts\40_make_trade_plan_intraday.py --date 2025-10-28 --tp-pct 0.012 --sl-pct 0.0035 --per-trade-cash 300 --capital-max 900 --ensure-one --ensure-exposure-min 280 --ensure-exposure-max 620 --fallback-prob-min 0.05 --fallback-ptpmin 0.12 --fallback-etth-max 0.30 --fallback-cost 0.0003

═══════════════════════════════════════════════════════════════════════════════
✅ RESUMEN EJECUTIVO
═══════════════════════════════════════════════════════════════════════════════

IMPLEMENTADO:
   ✅ Config Intraday 2.0 en intraday.yaml
   ✅ Parámetros: TP=1.2%, SL=0.35%, R:R=3.4:1
   ✅ Capital: $300/trade, $900 total
   ✅ Filtros: prob_win≥8%, ATR≥0.35%, P(TP<SL)≥15%
   ✅ Validación Oct 28: 1 trade, -$0.70 (vs -$1.60 anterior)

MEJORAS VS ANTERIOR:
   ✅ P(TP<SL): +30% (33.6% vs 25%)
   ✅ Pérdida por SL: -56% ($0.70 vs $1.60)
   ✅ TP realista: 1.2% vs 2.0% (hit rate esperado 30% vs 0%)

PENDIENTE CRÍTICO:
   ⚠️ Re-entrenar modelo con TP=1.2%, SL=0.35%
   ⚠️ Implementar filtro timing (rechazar >13:00)
   ⚠️ Calcular volume_ratio real
   ⚠️ Validar 8-10 fechas adicionales octubre

EXPECTATIVA:
   🎯 10-15 trades/mes
   🎯 30-35% win rate
   🎯 +$6 a +$16/mes en paper (conservador)
   🎯 Listo para re-entrenar y validar 2 semanas

═══════════════════════════════════════════════════════════════════════════════
"""

# Save report
output_path = "reports/intraday/INTRADAY_2_0_IMPLEMENTATION_REPORT.txt"

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(__doc__)

print(__doc__)
print(f"\n💾 Reporte guardado: {output_path}")
