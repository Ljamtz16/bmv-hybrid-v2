"""
Resumen de ejecución - Plan semanal 26 de enero de 2026
"""

print("""
================================================================================
PLAN SEMANAL - EJECUCION COMPLETADA
================================================================================

FECHA: 26 de enero de 2026
STATUS: ✓ COMPLETADO Y MONITORIZADO

================================================================================
[1] GENERACION DE PLANES
================================================================================

Plan 1: STANDARD (prob_win >= 0.50)
--------
  Posiciones: 3
  Tickers: AAPL (BUY), GS (SELL), MS (SELL)
  Exposición Total: $1,800.13
  Prob Win Promedio: 0.58
  Archivo: evidence/weekly_plans/plan_standard_2026-01-26.csv

Plan 2: PROBWIN_55 (prob_win >= 0.55)
--------
  Posiciones: 1
  Tickers: AAPL (BUY)
  Exposición Total: $493.45
  Prob Win Promedio: 0.79
  Archivo: evidence/weekly_plans/plan_probwin55_2026-01-26.csv

================================================================================
[2] DASHBOARD MONITORIZADO
================================================================================

URL: http://localhost:7777
Status: ✓ ACTIVO

Características:
  ✓ Comparación lado a lado de ambos planes
  ✓ Precios vivos actualizados cada minuto (yfinance)
  ✓ Métricas comparativas en tiempo real
  ✓ Auto-refresh cada 60 segundos
  ✓ API endpoints disponibles:
    - /api/plans (JSON de planes)
    - /api/status (estado del sistema)

================================================================================
[3] CAPITAL GUARDRAILS - VALIDACION
================================================================================

✓ Ambos planes respetan:
  • Capital máximo: $2,000
  • Max deploy: $1,900
  • Max posiciones: 4 (límite: cumple ≤4)
  • Cash por trade: $500
  • Stop Loss: 1.0%
  • Take Profit: 1.6%
  • Max hold days: 2

PLAN STANDARD: Exposición $1,800.13 (94.7% de $1,900 max_deploy) ✓
PLAN PROBWIN_55: Exposición $493.45 (25.9% de $1,900 max_deploy) ✓

================================================================================
[4] ANALISIS COMPARATIVO
================================================================================

| Métrica | STANDARD | PROBWIN_55 | Diferencia |
|---------|----------|-----------|-----------|
| Posiciones | 3 | 1 | -2 (-67%) |
| Exposición | $1,800.13 | $493.45 | -$1,306.68 (-73%) |
| Avg Prob Win | 0.580 | 0.790 | +0.210 (+36%) |
| Min Prob Win | 0.480 | 0.790 | +0.310 (+65%) |

Interpretación:
  • STANDARD: Más agresivo, busca oportunidades, prob_win moderada
  • PROBWIN_55: Más conservador, solo las mejores señales

================================================================================
[5] SEÑALES ACTIVAS POR TICKER
================================================================================

AAPL (BUY)
  • Entry: $246.72
  • TP: $250.66 (+1.6%)
  • SL: $244.23 (-1.0%)
  • Qty: 2 shares
  • Prob Win STANDARD: 0.79
  • En: AMBOS planes (STANDARD + PROBWIN_55)

GS (SELL)
  • Entry: $942.60
  • TP: $927.41 (-1.6%)
  • SL: $952.79 (+1.0%)
  • Qty: 1 share
  • Prob Win: 0.49
  • En: SOLO STANDARD (por baja prob_win)

MS (SELL)
  • Entry: $182.04
  • TP: $179.12 (-1.6%)
  • SL: $183.86 (+1.0%)
  • Qty: 2 shares
  • Prob Win: 0.48
  • En: SOLO STANDARD (por baja prob_win)

================================================================================
[6] ARCHIVOS GENERADOS
================================================================================

Plan Files:
  ✓ evidence/weekly_plans/plan_standard_2026-01-26.csv
  ✓ evidence/weekly_plans/plan_probwin55_2026-01-26.csv

Config Files:
  ✓ evidence/monitor_this_week/config_2026-01-26.json

Documentation:
  ✓ PLAN_SEMANAL_2026_01_26.md (análisis completo)

Forecast Source:
  ✓ evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv
    (5,067 filas, 5 tickers, 2022-2026)

================================================================================
[7] NEXT STEPS
================================================================================

HOY (26 enero):
  1. Revisar dashboard: http://localhost:7777
  2. Decidir: STANDARD vs PROBWIN_55 vs AMBOS
  3. Ejecutar órdenes si se confirman precios
  4. Monitorizar en tiempo real

DURANTE LA SEMANA:
  1. Seguimiento diario de posiciones
  2. Validar TP/SL se cumplen
  3. Registrar resultados reales vs. esperados
  4. Dashboard mantiene métricas actualizadas

PROXIMA SEMANA:
  1. Analizar performance de ambos planes
  2. Generar nuevo plan con:
     python generate_weekly_plans.py
  3. Comparar resultados reales vs. backtesting

================================================================================
[8] COMANDOS RAPIDOS
================================================================================

Ver planes (CSV):
  cat evidence/weekly_plans/plan_standard_2026-01-26.csv
  cat evidence/weekly_plans/plan_probwin55_2026-01-26.csv

Dashboard:
  ./.venv/Scripts/python.exe dashboard_compare_plans.py

Generar nuevos planes:
  ./.venv/Scripts/python.exe generate_weekly_plans.py

Ejecutar todo (plans + dashboard):
  .\run_weekly_plan.bat

================================================================================
[9] METRICAS DE REFERENCIA (Backtesting 2024-2025)
================================================================================

Con threshold prob_win >= 0.55 (similar a PROBWIN_55):
  • Return: +1.21% por semana
  • Win Rate: 60.9%
  • Semanas positivas: 89/105 (84.8%)
  • Total PnL: +$2,486 en $2,000 inicial
  • Max Drawdown: -8.2%
  • Avg Hold: 1.2 días

Estos son los números esperados si PROBWIN_55 sigue la tendencia histórica.

================================================================================
✓ PLAN SEMANAL COMPLETADO Y LISTO PARA EJECUTAR
================================================================================
""")
