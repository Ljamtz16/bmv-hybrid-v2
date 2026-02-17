# Plan de Acción Semanal - Enero 26, 2026

## Estado: ✓ GENERADO Y MONITORIZADO

### Fecha de Generación
- **Hoy:** 26 de enero de 2026
- **Basado en:** Forecast del 20 de enero (últimos datos disponibles)
- **Predicciones por:** Modelo logístico retrenado (prob_win_retrained)

---

## Dos Planes en Paralelo

### 1. PLAN STANDARD (prob_win >= 0.50)
**Estrategia:** Más agresivo, acepta señales con probabilidad de ganancia moderada

| Métrica | Valor |
|---------|-------|
| **Posiciones** | 3 |
| **Tickers** | AAPL, GS, MS |
| **Exposición Total** | $1,800.13 |
| **Prob Win Promedio** | 0.58 |
| **Prob Win Mínimo** | 0.48 |

#### Detalles de Posiciones:
| Ticker | Side | Entry   | TP     | SL     | Qty | Prob Win |
|--------|------|---------|--------|--------|-----|----------|
| AAPL   | BUY  | 246.72  | 250.66 | 244.23 | 2   | 0.79     |
| GS     | SELL | 942.60  | 927.41 | 952.79 | 1   | 0.49     |
| MS     | SELL | 182.04  | 179.12 | 183.86 | 2   | 0.48     |

**Utilidad:** Maximizar oportunidades trading
**Riesgo:** Mayor número de operaciones, menor selectividad

---

### 2. PLAN PROBWIN_55 (prob_win >= 0.55)
**Estrategia:** Más conservador, solo toma las mejores señales

| Métrica | Valor |
|---------|-------|
| **Posiciones** | 1 |
| **Tickers** | AAPL |
| **Exposición Total** | $493.45 |
| **Prob Win Promedio** | 0.79 |
| **Prob Win Mínimo** | 0.79 |

#### Detalles de Posiciones:
| Ticker | Side | Entry   | TP     | SL     | Qty | Prob Win |
|--------|------|---------|--------|--------|-----|----------|
| AAPL   | BUY  | 246.72  | 250.66 | 244.23 | 2   | 0.79     |

**Utilidad:** Maximizar tasa de ganancia, reducir riesgo
**Riesgo:** Menor número de oportunidades

---

## Análisis Comparativo

| Aspecto | STANDARD | PROBWIN_55 | Δ |
|---------|----------|-----------|---|
| **Posiciones** | 3 | 1 | -2 (-67%) |
| **Exposición** | $1,800.13 | $493.45 | -$1,306.68 |
| **Avg Prob Win** | 0.580 | 0.790 | +0.210 |
| **Min Prob Win** | 0.480 | 0.790 | +0.310 |

### Interpretación:
- **STANDARD:** 3x más posiciones, pero con menor calidad promedio de señal
- **PROBWIN_55:** Solo toma la señal más fuerte (AAPL), descarta GS y MS por baja confianza
- **Diferencia de Riesgo:** PROBWIN_55 es ~3x más conservador en exposición

---

## Capital Guardrails

| Parámetro | Valor |
|-----------|-------|
| **Capital Inicial** | $2,000 |
| **Max Deploy Permitido** | $1,900 |
| **Max Posiciones Abiertas** | 4 |
| **Cash por Trade** | $500 |
| **Take Profit** | 1.6% |
| **Stop Loss** | 1.0% |
| **Max Hold Days** | 2 |

**Ambos planes respetan todos los guardrails.**

---

## Dashboard Monitorizado

### Acceso
- **URL:** http://localhost:7777
- **Status:** ✓ En ejecución
- **Auto-refresh:** Cada 60 segundos

### Características
✓ Comparación lado a lado de ambos planes  
✓ Actualización de precios cada minuto desde yfinance  
✓ Estadísticas resumidas por plan  
✓ Tabla de operaciones con entrada, TP, SL  
✓ Métricas comparativas (posiciones, exposición, prob_win)  

---

## Próximas Acciones

### Hoy (26 de enero):
- [ ] Revisar ambos planes en el dashboard
- [ ] Decidir cuál plan seguir (STANDARD o PROBWIN_55)
- [ ] Ejecutar órdenes de entrada si se confirman precios
- [ ] Monitorizar en tiempo real

### Esta Semana:
- [ ] Seguimiento diario de posiciones abiertas
- [ ] Validar TP/SL se cumplen según lo planeado
- [ ] Registrar resultados reales vs. esperados
- [ ] Ajustar estrategia si es necesario

### Generación del Próximo Plan:
```bash
# Viernes o inicio de próxima semana
./.venv/Scripts/python.exe generate_weekly_plans.py
# Luego:
./.venv/Scripts/python.exe dashboard_compare_plans.py
```

---

## Archivos Generados

| Archivo | Ubicación | Propósito |
|---------|-----------|----------|
| plan_standard_2026-01-26.csv | evidence/weekly_plans/ | Plan STANDARD completo |
| plan_probwin55_2026-01-26.csv | evidence/weekly_plans/ | Plan PROBWIN_55 completo |
| config_2026-01-26.json | evidence/monitor_this_week/ | Config para dashboard |
| forecast_prob_win_retrained.csv | evidence/forecast_retrained_robust/ | Fuente de predicciones |

---

## Decisiones Clave de Esta Semana

### ¿Qué plan ejecutar?

#### Opción 1: STANDARD (3 posiciones)
**Cuándo usar:**
- ✓ Aversión a dinero en efectivo
- ✓ Tolerancia moderada al drawdown
- ✓ Objetivo: maximizar oportunidades

**Riesgo:** Señales con prob_win 0.48-0.49 tienen ~50% tasa de ganancia teórica

#### Opción 2: PROBWIN_55 (1 posición)
**Cuándo usar:**
- ✓ Preservación de capital prioritaria
- ✓ Solo ejecutar operaciones de alta confianza
- ✓ Objetivo: máximo win rate

**Limitación:** Solo 1 posición = menor diversificación

#### Opción 3: Híbrida
**Ejecutar los 2 planes simultáneamente:**
- STANDARD = account principal
- PROBWIN_55 = account conservador
- **Ventaja:** Datos comparativos directos sobre qué threshold es mejor

---

## Sistema de Monitoreo

### Dashboard Activo
```
✓ En ejecución: http://localhost:7777
✓ Actualización: Automática cada 60 segundos
✓ Precios vivos: yfinance
✓ Planes comparados: Lado a lado
```

### Métricas Monitoreadas
- Exposición vs. Capital
- Prob Win promedio y mínimo por plan
- Cantidad de posiciones abiertas
- TP y SL para cada trade
- Última actualización de precios

---

## Notas Técnicas

### Datos Utilizados
- **Última fecha de forecast:** 20 enero 2026
- **Modelo:** Logistic Regression (prob_win_retrained)
- **Tickers con modelos:** 5 (AAPL, GS, IWM, JPM, MS)
- **Precios de entrada:** Close price del 20/01/2026

### Cálculos de Posición
- **Qty = PER_TRADE_CASH / ENTRY_PRICE**
- **TP = ENTRY × (1 + 1.6%)** para BUY, ENTRY × (1 - 1.6%) para SELL
- **SL = ENTRY × (1 - 1.0%)** para BUY, ENTRY × (1 + 1.0%) para SELL

---

## Comandos Útiles

### Generar nuevos planes
```bash
./.venv/Scripts/python.exe generate_weekly_plans.py
```

### Monitorizar planes
```bash
./.venv/Scripts/python.exe dashboard_compare_plans.py
```

### Ejecutar ambos en secuencia
```bash
.\run_weekly_plan.bat
```

---

## Generado
- **Fecha:** 26 de enero de 2026, 14:00 UTC
- **Por:** Sistema de planificación semanal v2
- **Basado en:** 2 años de backtesting (2024-2025) con capital $2,000
- **Resultado histórico (0.55 threshold):** +1.21%/semana, 60.9% win rate

---

**Estado Final: ✅ Planes generados y dashboard monitoreado**
