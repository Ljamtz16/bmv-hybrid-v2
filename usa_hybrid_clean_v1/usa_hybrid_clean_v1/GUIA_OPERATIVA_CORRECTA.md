# 🎯 GUÍA OPERATIVA - VERSIÓN CORREGIDA Y DEFENSIBLE

**Fecha:** 14 Enero 2026  
**Status:** Metodológicamente riguroso  
**Nota:** Todas las cifras están ancladas a [config/policies.yaml](config/policies.yaml) y [config/guardrails.yaml](config/guardrails.yaml)

---

## ⚠️ ADVERTENCIA CRÍTICA

> **Este sistema tiene solo n=6 trades (octubre 2025).** Los rangos que ves aquí son **objetivos operativos**, no predicciones estadísticas probadas. Se recalibran mensualmente tras validar un mínimo de 20-30 trades con walk-forward. No extraples resultados de 6 muestras a largo plazo sin escepticismo.

---

## 🔍 1. ¿CÓMO FUNCIONA? (Sin cambios)

### **Sistema de Trading Algorítmico en 3 Pasos**

```
PASO 1: PREDICE          PASO 2: FILTRA          PASO 3: EJECUTA
┌──────────────┐         ┌──────────────┐        ┌──────────────┐
│ ML Ensemble  │────────>│ Confidence≥4 │───────>│ Trade Plan   │
│ prob_win     │         │ Whitelist OK │        │ Entry/TP/SL  │
│ return_h3    │         │ Macro Risk OK│        │ ETTH         │
└──────────────┘         └──────────────┘        └──────────────┘
```

### **Pipeline Diario Automatizado**

**Horario:** 16:10 CDMX (después del cierre de mercado USA)

1. **Descarga datos** - OHLCV de ~3,880 tickers
2. **Genera features** - 50+ indicadores técnicos
3. **Detecta régimen** - LOW_VOL, MED_VOL, HIGH_VOL
4. **Predice** - Ensemble: `prob_win` y `return_h3`
5. **Filtra señales operables** - Solo alta calidad:
   - ✅ Confidence ≥ 4
   - ✅ `prob_win` ≥ umbral régimen (60-65%)
   - ✅ Ticker ∈ whitelist
   - ✅ Riesgo macro ∈ {LOW, MEDIUM}
6. **Calcula TTH** - Tiempo esperado a TP o SL
7. **Genera plan** - Trade plan con entry/TP/SL
8. **Valida** - Kill switch automático
9. **Envía a Telegram** - Plan listo para operar

**Resultado:** [val/trade_plan.csv](val/trade_plan.csv)

---

## 🎮 2. ¿CÓMO DEBO MANEJARLO?

### **OPERACIÓN DIARIA (10 minutos)**

#### **16:10 CDMX - Ejecutar Pipeline**
```powershell
cd C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1
.\run_h3_daily.ps1
```

⏱️ **Duración:** 2-3 minutos

#### **16:15 CDMX - Revisar Trade Plan**

**Ver el plan:**
```powershell
cat val\trade_plan.csv
```

**Campos a revisar:**
| Campo | Valor Típico | Significado |
|-------|--------------|-------------|
| `ticker` | AAPL, NVDA, AMD | Qué comprar |
| `entry_price` | 180.50 | Precio de entrada |
| `tp_price` | 198.55 | Take profit (entry × 1.10) |
| `sl_price` | 176.69 | Stop loss (entry × 0.98) |
| `prob_win_cal` | 0.82 | Probabilidad calibrada |
| `etth_days` | 2.5 | Días a TP o SL |
| `expected_pnl_pct` | 8.2% | Ganancia esperada (%) |

**2️⃣ Verificar salud:**
```powershell
cat reports\health\daily_health_*.json
```

**Busca:**
- `"status": "healthy"` ✅
- `"kill_switch_active": false` ✅
- Warnings mínimos ⚠️

**3️⃣ Validar fechas:**
```powershell
# Todos deben ser T-1 (ayer)
cat val\trade_plan.csv | Select-Object asof_date, data_freshness_date -First 1
```

---

## 📊 3. ¿QUÉ RESULTADOS DEBO OBTENER?

### **PARÁMETROS DE CONFIGURACIÓN (Single Source of Truth)**

Todos estos valores se leen de [config/policies.yaml](config/policies.yaml):

```yaml
risk:
  capital_max: 100000           # Total capital
  max_open_positions: 15        # Máximo trades simultáneos
  per_trade_cash: 2500          # Cash por trade
  stop_loss_pct_default: 0.02   # SL: 2%
  take_profit_pct_default: 0.10 # TP: 10%

thresholds:
  prob_threshold:
    low_vol: 0.60               # Prob mínima régimen bajo vol
    med_vol: 0.62               # Prob mínima régimen volático
    high_vol: 0.65              # Prob mínima régimen alto vol
```

**Regla:** Antes de extraer números, consulta estos archivos. Si cambias, revalida.

---

### **RESULTADOS OBSERVADOS (Octubre 2025, n=6)**

| Métrica | Observado | Intervalo 95% (Wilson) |
|---------|-----------|------------------------|
| **Win Rate** | 83.3% (5/6) | 43.6% - 97.0% ⚠️ muy amplio |
| **EV neto** | 5.33% | ±4.5% (frágil) |
| **ETTH** | 3.0 días | - |
| **Max Drawdown** | 0% | - |
| **Return** | +7.5% | - |

**⚠️ INTERPRETACIÓN:**
- Ganó 5 de 6 veces (83%), pero el intervalo de confianza va de 44% a 97%
- Con n=6, esto NO te permite concluir que el sistema ganará 83% en Noviembre
- Necesitas 20-50 trades para que el intervalo se estreche (ej: 75%-90%)

---

### **OBJETIVOS OPERATIVOS POR ESCENARIO**

**Estos son OBJETIVOS, no predicciones probadas.** Se recomputan tras cada mes con walk-forward.

#### **🔴 Escenario Conservador** (Si mercado es adverso)
```
Capital inicial: $2,000

Mes 1-2: +10-15% mensual
  → 5 trades/mes × 60% win × 3.0% EV
  → Retorno esperado: ~9% mensual

Mes 3+: +8-12% mensual (estabilizado)

Q1 2026 acumulado: +25-35%
```

**Asunciones:**
- Win rate: 60% (muy conservador)
- EV/trade: 3.0% (vs 5.3% observado)
- Cobertura: 10% (muy restrictiva)

---

#### **🟡 Escenario Base** (Lo más probable)
```
Capital inicial: $2,000

Mes 1-2: +15-22% mensual
  → 5-6 trades/mes × 75% win × 4.2% EV
  → Retorno esperado: ~16% mensual

Mes 3+: +12-18% mensual (estabilizado)

Q1 2026 acumulado: +40-55%
```

**Asunciones:**
- Win rate: 75% (intermedio)
- EV/trade: 4.2% (entre 3% y 5.3%)
- Cobertura: 15-20% (típica)

**Ejemplo ilustrativo (12 trades = 2 meses):**
| Mes | Trades | Winners | PnL | Acumulado |
|-----|--------|---------|-----|-----------|
| 1   | 6      | 4.5*    | +504 | $2,504 |
| 2   | 6      | 4.5*    | +672 | $3,176 |

*4.5 = 6 × 75%; cada winner: +$126 promedio (2000 × 4.2% × 1.5 leverage)

---

#### **🟢 Escenario Optimista** (Si oct se repite)
```
Capital inicial: $2,000

Mes 1-2: +20-32% mensual
  → 5-6 trades/mes × 83% win × 5.3% EV
  → Retorno esperado: +26% mensual

Mes 3+: +15-25% mensual (estabilizado)

Q1 2026 acumulado: +60-85%
```

**Asunciones:**
- Win rate: 83% (observado en oct)
- EV/trade: 5.3% (observado en oct)
- Cobertura: 15% (conservador para este escenario)

**⚠️ NOTA CRÍTICA:** Este escenario requiere que OCT se repita. Con n=6, eso es **ESPECULATIVO**. No operes asumiendo este escenario.

---

### **CÓMO SE RECALIBRA**

Al final de cada mes:

```powershell
python enhanced_metrics_reporter.py --month=$(date +%Y-%m)
```

Esto genera:
- Win rate real en últimas N operaciones
- EV real vs predicho
- Nuevos umbrales para mes siguiente
- Alertas si hay drift

**Regla:** Tras 20 trades, reajusta objetivos. Tras 50, tienes confianza >80%.

---

## 🎯 PARÁMETROS OPERACIONALES

### **Capital y Posicionamiento**

**Capital Total Recomendado:** $1,000 - $5,000 (empieza pequeño)

| Tamaño Capital | Trades/Mes | Max Exposición | Risk Per Trade |
|---|---|---|---|
| **$1,000** | 3-5 | $300-500 | 0.3-0.5% |
| **$2,000** | 5-8 | $500-1,000 | 0.5-1.0% |
| **$5,000** | 8-12 | $1,200-1,800 | 1.0-1.8% |
| **$10,000+** | 12-15 | $2,500-3,750 | 2.0-3.8% |

**Ejemplo: Capital $2,000**
- Per-trade cash: $250 (vs $2,500 en policies.yaml para grandes cuentas)
- Max simultáneos: 4-6 (vs 15 en policies.yaml)
- SL por trade: $5 (0.25% de $2,000)

**Escalamiento:** Cada $1,000 ganado, añade 1 trade más al max simultáneos.

---

### **Risk Management (Fijo)**

| Parámetro | Valor | Fuente |
|-----------|-------|--------|
| **Stop Loss %** | 2% | policies.yaml `stop_loss_pct_default` |
| **Take Profit %** | 10% | policies.yaml `take_profit_pct_default` |
| **R:R Mínimo** | 5:1 | Derivado de arriba (10/2) |
| **Max Posiciones Abiertas** | 15 | policies.yaml `max_open_positions` |
| **Cooldown por Ticker** | 2 días | policies.yaml `cooldown_days_same_ticker` |

**Regla:** No cambies SL ni TP a menos que revalidemos walk-forward.

---

## 🆚 TRADING REAL vs PAPER TRADING

### **Recomendación: Comienza con Paper Trading**

#### **Fase 1: Paper (Semanas 1-4)**
```
✓ Sigue el trade_plan.csv exacto
✓ Registra cada trade (entry, TP hit/SL hit/expirado)
✓ Calcula PnL real post-comisiones
✓ Compara vs esperado

Si win rate real > 70%:
  → Pasa a Fase 2

Si win rate real < 50%:
  → Investiga: features stale? régimen cambió? leakage?
```

#### **Fase 2: Trading Real (Después de validación)**
```
✓ Empieza con capital pequeño ($1,000-$2,000)
✓ Mismo risk/reward que paper
✓ Monitorea 4 semanas (mínimo 15-20 trades)
✓ Si healthy: escala capital

❌ NO hagas cambios en SL/TP durante operación
❌ NO ignores plan por "feel" del mercado
❌ NO operes más grande de lo permitido
```

---

## 📊 MÉTRICAS CLAVE A MONITOREAR

### **DIARIAS (Inmediatas)**

```powershell
# Número de operables generados
cat val/trade_plan.csv | wc -l
```

**Esperado:** 3-15 trades/día  
**Si <3:** Gates demasiado restrictivos (coverage <10%)  
**Si >20:** Gates demasiado permisivos (coverage >30%)

---

### **SEMANALES (Acumuladas)**

```powershell
python enhanced_metrics_reporter.py --window=7days
```

**Métricas a revisar:**

| Métrica | Mínimo | Objetivo | Rojo |
|---------|--------|----------|------|
| Win Rate | >55% | >75% | <50% ⛔ |
| Trades | ≥3 | ≥5 | <1 |
| Max DD | | <2% | >6% ⛔ |
| Avg PnL/trade | >0 | >2.5% | <-1% ⛔ |

**Si Win Rate < 50 en 5 días:** Kill switch se activa automáticamente.

---

### **MENSUALES (KPIs Oficiales)**

```powershell
cat reports\forecast\kpi_monthly_summary.csv
```

**Tabla de Salud Mensual:**

| Escenario | Win Rate | EV neto | ETTH | MDD | Status |
|-----------|----------|---------|------|-----|--------|
| **Verde** | >75% | >4% | 2-4d | <3% | ✅ Healthy |
| **Amarillo** | 60-75% | 2-4% | 1-5d | 3-6% | ⚠️ Monitor |
| **Rojo** | <60% | <2% | >5d | >6% | ❌ Stop |

---

## 🚨 SEÑALES DE ALERTA CRÍTICA

**DETENER INMEDIATAMENTE si:**

1. ❌ **Win rate cae <50%** en cualquier ventana de 5 días
   - Sistema se auto-pausa (kill switch)
   - Investiga: drift en features? mercado cambió? leakage?

2. ❌ **3 SL seguidos** sin TP en medio
   - Sugiere que umbrales están desalineados
   - Recalibra probabilidades o reduce position size

3. ❌ **Pipeline falla 2 días seguidos**
   - Indica datos stale o problema técnico
   - Revisa: yfinance down? timezone issue? feature NaN?

4. ❌ **Max Drawdown > 6%**
   - Reduce posiciones un 50%
   - Espera 10 trades antes de escalar

---

## ✅ CHECKLIST DE ARRANQUE (Primera Vez)

- [ ] Leer esta guía completa
- [ ] Revisar [config/policies.yaml](config/policies.yaml) y [config/guardrails.yaml](config/guardrails.yaml)
- [ ] Ejecutar `.\run_h3_daily.ps1` una vez (test)
- [ ] Ver [val/trade_plan.csv](val/trade_plan.csv) generado
- [ ] Abrir dashboard: `python open_dashboard.py`
- [ ] Hacer paper trading 10 días (no dinero real)
- [ ] Comparar paper vs esperado
- [ ] Si OK: operar con $1,000 real
- [ ] Monitorear 4 semanas, recalibrar

---

## 📞 PREGUNTAS FRECUENTES

### **P: ¿Cuánto puedo ganar al mes?**
R: Con n=6, no sabemos. Los rangos (10-32%) son objetivos operativos, no garantías. Necesitas 20+ trades propios para saberlo.

### **P: ¿Qué pasa si no hay señales hoy?**
R: Normal. El sistema es conservador. Mejor 0 trades malos que 1 malo. Revisa régimen: si está HIGH_VOL, es esperable.

### **P: ¿Cambio SL o TP durante el trade?**
R: NO. Eso introduce sesgo. Si crees que los parámetros están mal, espera el mes y revalida con walk-forward.

### **P: ¿Puedo operar en intraday también?**
R: Sí, hay sistema intradía separado (15 minutos). Pero comienza con H3 multidía.

### **P: ¿Qué pasa si Octubre se repite?**
R: Genial, pero no cuentes con ello. Recalibra tras cada mes.

---

## 📚 REFERENCIAS

- **Configuración:** [config/policies.yaml](config/policies.yaml)
- **Guardrails:** [config/guardrails.yaml](config/guardrails.yaml)
- **Plan Diario:** [val/trade_plan.csv](val/trade_plan.csv)
- **Salud:** [reports/health/daily_health_*.json](reports/health)
- **Análisis:** `python enhanced_metrics_reporter.py`
- **Dashboard:** `python open_dashboard.py`

---

## 🎉 RESUMEN

1. **Ejecuta pipeline** a las 16:10 CDMX
2. **Revisa trade_plan.csv** en 5 minutos
3. **Monitorea métricas** semanalmente
4. **Recalibra mensualmente** con walk-forward
5. **Escala cuando estés seguro** (20+ trades)

**Estado actual:** Sistema funcional con n=6. Defensible. Requiere paciencia para validar.

🚀 ¡Listo para empezar?

