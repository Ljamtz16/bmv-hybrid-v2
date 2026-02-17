# CHECKPOINT - 19 ENERO 2026 (23:45 UTC)

## 📊 ESTADO ACTUAL DEL SISTEMA

### Simulaciones Completadas en Esta Sesión

#### 1️⃣ **18 Tickers FAST - Q1 2025** ✅
- **Configuración**: Modo FAST, TP 2.0%, SL 1.2%, Max Hold 2 días
- **Universo**: AAPL, AMD, AMZN, CAT, CVX, GS, IWM, JNJ, JPM, MS, MSFT, NVDA, PFE, QQQ, SPY, TSLA, WMT, XOM
- **Capital/Exposure**: $1,000 / $1,000
- **Resultados Agregados**:
  - P&L Total: **+$7.14**
  - Win Rate: **43.6%**
  - Trades: **78** (1 TP, 40 SL, 37 TO)
  - Max Drawdown: **1.84%**
  - Equity Final: **$1,007.14**
- **Detalle por Mes**:
  - Enero: -$1.69 | 45.0% WR | 20 trades
  - Febrero: +$0.76 | 42.1% WR | 19 trades
  - Marzo: +$8.07 | 43.6% WR | 39 trades
- **Evidence**: `evidence/paper_multi_2025Q1_ALL_18_TICKERS_FAST/`

#### 2️⃣ **5 Tickers FAST (TP=2.0%) - Q1 2025** ✅
- **Configuración**: Modo FAST, TP 2.0%, SL 1.2%, Max Hold 2 días
- **Universo**: NVDA, AMD, XOM, META, TSLA (5 tickers seleccionados)
- **Capital/Exposure**: $1,000 / $1,000
- **Resultados Agregados**:
  - P&L Total: **+$6.37**
  - Win Rate: **42.4%**
  - Trades: **59** (1 TP, 30 SL, 28 TO)
  - Max Drawdown: **1.84%**
  - Equity Final: **$1,006.37**
- **Detalle por Mes**:
  - Enero: -$1.69 | 45.0% WR | 20 trades
  - Febrero: +$0.76 | 42.1% WR | 19 trades
  - Marzo: +$7.30 | 40.0% WR | 20 trades
- **Evidence**: `evidence/paper_multi_2025Q1_5_TICKERS_FAST/`
- **Vs 18 Tickers**: -$0.77 P&L (-10.8%), -1.2 pp WR, -19 trades

#### 3️⃣ **5 Tickers FAST (TP=0.8%) - Q1 2025** ✅
- **Configuración**: Modo FAST, TP 0.8%, SL 1.2%, Max Hold 2 días
- **Universo**: NVDA, AMD, XOM, META, TSLA (5 tickers seleccionados)
- **Capital/Exposure**: $1,000 / $1,000
- **Resultados Agregados**:
  - P&L Total: **-$6.76** 🔴 PERDIDA
  - Win Rate: **55.9%** 🟢 (mejor)
  - Trades: **78** (44 TP, 34 SL, 0 TO) 🟢 (sin timeouts)
  - Max Drawdown: **0.65%** 🟢 (menor riesgo)
  - Equity Final: **$993.24**
- **Detalle por Mes**:
  - Enero: -$4.87 | 50.0% WR | 20 trades (10 TP, 10 SL)
  - Febrero: +$1.37 | 63.2% WR | 19 trades (12 TP, 7 SL)
  - Marzo: -$3.26 | 56.4% WR | 39 trades (22 TP, 17 SL)
- **Evidence**: `evidence/paper_multi_2025Q1_5_TICKERS_TP08/`
- **Vs TP=2.0%**: -$13.13 P&L (-206%), +13.5 pp WR, +19 trades, -28 TO

---

## 🔍 ANÁLISIS COMPARATIVO FINAL

### Resumen de las 3 Simulaciones

| Metrica | 18 TK FAST | 5 TK TP2.0% | 5 TK TP0.8% | Mejor |
|---------|-----------|-----------|-----------|-------|
| **P&L** | +$7.14 | +$6.37 | -$6.76 | 18 TK |
| **Win Rate** | 43.6% | 42.4% | 55.9% | 5 TK TP0.8% |
| **Trades** | 78 | 59 | 78 | 18 TK / 5 TK TP0.8% |
| **TP Rate** | 1.3% | 1.7% | 56.4% | 5 TK TP0.8% |
| **SL Rate** | 51.3% | 50.8% | 43.6% | 5 TK TP0.8% |
| **Timeout Rate** | 47.4% | 47.5% | 0% | 5 TK TP0.8% |
| **Max Drawdown** | 1.84% | 1.84% | 0.65% | 5 TK TP0.8% |
| **Avg Hold (h)** | 27.5 | 27.4 | 1.4 | 5 TK TP0.8% |

### Key Findings

#### ✅ Positivo
1. **18 Tickers produce mejor P&L**: +$7.14 es superior a ambas alternativas
2. **TP=0.8% elimina timeouts**: 0 timeouts vs 28-37 con TP=2.0%
3. **TP=0.8% reduces risk**: MDD 0.65% es mucho menor (1.84% vs)
4. **TP=0.8% improves WR**: 55.9% es mejor que 42-43%

#### ❌ Negativo
1. **TP=0.8% destroys P&L**: -$6.76 es pérdida vs +$6.37 con TP=2.0%
2. **TP=0.8% overtrading**: 78 trades generan más fricción sin beneficio
3. **TP=0.8% premature exits**: Cierra ganancias chicas mientras los movimientos van a más
4. **5 Tickers FAST underperforms**: 18 tickers es mejor en Q1 2025

#### 🎯 Insight Crítico
**Paradoja Observada**: Mayor win rate (55.9%) + Menor riesgo (0.65% MDD) ≠ Mayor P&L
- Causa: Asimetría de ganancias (promedio $0.88 por TP) vs pérdidas (promedio $1.34 por SL)
- Solución: Necesita SL más apretado O TP más amplio para balancear

---

## 📁 ARCHIVOS GENERADOS

### Scripts Creados
- `simulate_5_tickers.py` - Simulador para 5 tickers FAST TP=2.0%
- `simulate_5_tickers_tp08.py` - Simulador para 5 tickers FAST TP=0.8%

### Evidence Directories
```
evidence/
├── paper_multi_2025Q1_ALL_18_TICKERS_FAST/    (18 TK FAST)
│   ├── 2025-01/summary.json
│   ├── 2025-02/summary.json
│   └── 2025-03/summary.json
├── paper_multi_2025Q1_5_TICKERS_FAST/         (5 TK TP2.0%)
│   ├── 2025-01/summary.json
│   ├── 2025-02/summary.json
│   └── 2025-03/summary.json
└── paper_multi_2025Q1_5_TICKERS_TP08/         (5 TK TP0.8%)
    ├── 2025-01/summary.json
    ├── 2025-02/summary.json
    └── 2025-03/summary.json
```

---

## 🎓 LECCIONES APRENDIDAS

### 1. Universo de Tickers
- **18 tickers** es más robusto que **5 tickers** para FAST mode en Q1 2025
- Concentración en 5 tickers reduce volumen de oportunidades (-32% trades)
- Los 13 tickers excluidos generaban trades rentables adicionales

### 2. TP/SL Trade-off
- **TP=2.0%**: Baja win rate (42.4%) pero ganancia/pérdida más balanceada
- **TP=0.8%**: Alta win rate (55.9%) pero ganancias pequeñas < pérdidas medianas
- **Conclusión**: Para este mercado, TP=2.0% > TP=0.8% en terms de P&L neto

### 3. Timeout Analysis
- TP=2.0% genera 47.5% timeouts (trades que no capturan TP/SL)
- TP=0.8% elimina timeouts (0%) pero no es optimal
- **Implicación**: Posible TP intermedio (1.2-1.5%) sea mejor

### 4. Hold Time
- TP=2.0%: ~27 horas promedio (intraday + next day)
- TP=0.8%: ~1.4 horas promedio (casi puro intraday)
- TP=0.8% es más "scalper-like" → no apto para estrategia multi-día

---

## 📌 PRÓXIMOS PASOS RECOMENDADOS

### Priority 1: Optimization
1. **Test TP intermedio**: 1.2% o 1.5% TP para balancear
   - Esperar reducir timeouts vs TP=2.0%
   - Esperado: mejor P&L que TP=0.8%
   
2. **Individualize SL por ticker**: Algunos tickers merece SL más apretado
   - TSLA/META: más volátil → SL 1.5%
   - XOM/AMD: menos volátil → SL 1.0%

### Priority 2: Mode Testing
3. **Test BALANCED mode** con 5 y 18 tickers
   - BALANCED usa mid-point exits vs aggressive FAST
   - Esperar mejor WR con menor P&L impact

### Priority 3: Analysis
4. **Deep dive por ticker**: ¿Cuál contribuye más SL/TP?
   - Analizar all_trades.csv en cada directorio
   - Identificar tickers underperforming

### Priority 4: Risk
5. **Equity carry-over testing**: Usar equity final de mes anterior como capital siguiente
   - Actualmente cada mes empieza con $1,000
   - Impacto en metrics over longer periods

---

## ⚙️ CONFIGURACIÓN RECOMENDADA (para próximos tests)

```python
CONFIG_OPTIMAL_CANDIDATE = {
    "months": ["2025-01", "2025-02", "2025-03"],
    "tickers": ["NVDA", "AMD", "XOM", "META", "TSLA"],  # o 18 si mejor P&L
    "execution_mode": "fast",  # o "balanced" para comparar
    "capital": 1000,
    "exposure_cap": 1000,
    "tp_pct": 0.015,  # 1.5% (intermedio)
    "sl_pct": 0.012,  # 1.2% (mantener)
    "max_hold_days": 2
}
```

---

## 📊 MÉTRICAS DE SALUD DEL SISTEMA

- ✅ Data pipeline: OPERATIONAL (consolidated_15m.parquet)
- ✅ Simulador: STABLE (0 errores en 3 runs)
- ✅ Broker module: WORKING (todas las init OK)
- ✅ Evidence generation: COMPLETE (9 summary.json files)
- ⚠️ Strategy profitability: MARGINAL (+$7.14 en 3 meses = 0.71% ROI)
- ⚠️ Parameter tuning: NEEDED (TP/SL aún no optimal)

---

## 🕐 TIMESTAMP

- **Fecha**: 19 de enero 2026, 23:45 UTC
- **Duración total de simulaciones**: ~2.5 horas
- **Estado**: CHECKPOINT COMPLETADO
- **Próximo checkpoint recomendado**: Después de test TP=1.5%

---

**Nota**: Este checkpoint registra el estado después de 3 backtests completos (18 TK, 5 TK TP2%, 5 TK TP0.8%). Todas las simulaciones corrieron exitosamente sin errores críticos.
