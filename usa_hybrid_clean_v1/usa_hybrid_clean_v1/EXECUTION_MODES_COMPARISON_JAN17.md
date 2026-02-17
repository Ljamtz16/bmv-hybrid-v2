# EXECUTION MODES COMPARISON | Jan 17, 2026

**Fecha:** 2026-01-17 13:00 UTC  
**Período:** 2026-01 (capital $1000)  
**Asof-Date:** 2026-01-15 (T-1)  
**Precios:** ohlcv_daily.parquet (27,324 registros)  
**Forecast:** signals_with_gates.parquet (8 registros únicos)

---

## SUMMARY TABLE

| Parámetro | **FAST** | **BALANCED** | **CONSERVATIVE** |
|-----------|----------|-------------|------------------|
| **Objetivo** | Capital rápido | Mezcla óptima | Calidad primero |
| **Modo** | fast | balanced | conservative |
| **ETTH Max** | 3.5 | 6.0 | (sin límite) |
| **Score Formula** | strength/etth | 0.7\*strength + 0.3\*(1/etth) | strength |
| **Exposure Cap** | $800 | $800 | None |
| **Trades Elegibles** | 1 | 4 | 5 |
| **Trades Mantenidos** | 1 | 4 | 5 |
| **Trades Descartados** | 4 | 1 | 0 |
| **Exposure Final** | **$227.92** | **$642.41** | **$861.98** |
| **Prob Win (mean)** | 95.1% | 95.7% | 95.4% |
| **ETTH (mean)** | 2.59d | 4.21d | 4.62d |

---

## EXECUTION ORDER (por modo)

### 🚀 **FAST** (rotación rápida ≤ 3.5 días)

```
1. AMD    | BUY  | $227.92 | prob=95.1% | etth=2.59d | score=0.368 ✓ KEEP
2. JNJ    | BUY  | $219.57 | prob=96.9% | etth=6.24d | score=NaN   ✗ DROP (etth > 3.5)
3. XOM    | BUY  | $129.13 | prob=96.3% | etth=4.59d | score=NaN   ✗ DROP (etth > 3.5)
4. CVX    | BUY  | $166.16 | prob=96.0% | etth=4.21d | score=NaN   ✗ DROP (etth > 3.5)
5. WMT    | BUY  | $119.20 | prob=92.6% | etth=5.46d | score=NaN   ✗ DROP (etth > 3.5)

Portfolio: 1 trade, alta rotación, menor exposición
Ideal para: traders que quieren capital en movimiento rápido
```

### ⚖️ **BALANCED** (velocidad + calidad 6.0d)

```
1. AMD    | BUY  | $227.92 | prob=95.1% | etth=2.59d | score=0.782 ✓ KEEP (prioridad 1)
2. CVX    | BUY  | $166.16 | prob=96.0% | etth=4.21d | score=0.744 ✓ KEEP (prioridad 2)
3. XOM    | BUY  | $129.13 | prob=96.3% | etth=4.59d | score=0.739 ✓ KEEP (prioridad 3)
4. WMT    | BUY  | $119.20 | prob=92.6% | etth=5.46d | score=0.703 ✓ KEEP (prioridad 4)
5. JNJ    | BUY  | $219.57 | prob=96.9% | etth=6.24d | score=NaN   ✗ DROP (etth > 6.0)

Portfolio: 4 trades, balance rotación-confianza
Ideal para: traders que quieren diversificación sin apresurar
```

### 💎 **CONSERVATIVE** (máxima fortaleza, sin límite ETTH)

```
1. JNJ    | BUY  | $219.57 | prob=96.9% | etth=6.24d | score=0.969 ✓ KEEP (strength #1)
2. XOM    | BUY  | $129.13 | prob=96.3% | etth=4.59d | score=0.963 ✓ KEEP (strength #2)
3. CVX    | BUY  | $166.16 | prob=96.0% | etth=4.21d | score=0.960 ✓ KEEP (strength #3)
4. AMD    | BUY  | $227.92 | prob=95.1% | etth=2.59d | score=0.951 ✓ KEEP (strength #4)
5. WMT    | BUY  | $119.20 | prob=92.6% | etth=5.46d | score=0.926 ✓ KEEP (strength #5)

Portfolio: 5 trades, máxima cobertura
Ideal para: traders que anteponen win-rate sobre velocidad
```

---

## DECISION MATRIX

### ¿Cuándo usar cada modo?

| Situación | Recomendación |
|-----------|---|
| Mercado muy volátil, necesito capital ágil | **FAST** ✓ |
| Mercado normal, quiero buena balanza | **BALANCED** ✓ (default) |
| Mercado trending fuerte, máxima confianza | **CONSERVATIVE** ✓ |
| Bajo capital ($200-500), gap grande en ETTH | **FAST** ✓ |
| Capital moderado ($500-1000), riesgo tolerable | **BALANCED** ✓ |
| Alto capital (>$1000), quiero diversificación | **CONSERVATIVE** ✓ |

---

## TECHNICAL DETAILS

### FAST Mode Scoring
```
exec_score = strength / etth_days
Ejemplo AMD: 0.951 / 2.59 ≈ 0.368
```
**Ventaja:** Prioriza activos que llegarán a TP rápidamente  
**Desventaja:** Descarta oportunidades de largo plazo

### BALANCED Mode Scoring
```
exec_score = 0.7*strength + 0.3*(1/etth_days_norm)
Ejemplo AMD: 0.7*0.951 + 0.3*(1/2.59) ≈ 0.782
Ejemplo CVX: 0.7*0.960 + 0.3*(1/4.21) ≈ 0.744
```
**Ventaja:** Combina señal confiable con velocidad razonable  
**Desventaja:** Score menos extremo

### CONSERVATIVE Mode Scoring
```
exec_score = strength (sin ajuste por ETTH)
Ejemplo JNJ: 0.969
Ejemplo AMD: 0.951
```
**Ventaja:** Puro win-rate, ignora velocidad  
**Desventaja:** Sin presión a ejecutar rápido

---

## EXPOSURE ANALYSIS

### Cap Effects

#### FAST + $800 Cap
- Base: $861.98 (5 trades)
- Después cap: $227.92 (1 trade)
- Reducción: -73.6% (remover 4 trades por ETTH antes de cap)

#### BALANCED + $800 Cap
- Base: $861.98 (5 trades)
- Después cap: $642.41 (4 trades)
- Reducción: -25.4% (solo JNJ removido por ETTH > 6.0)

#### CONSERVATIVE (sin cap)
- Base: $861.98 (5 trades)
- Después cap: $861.98 (5 trades)
- Reducción: 0% (todas aprobadas)

---

## AUDIT LOGS

Cada ejecución genera `val/trade_plan_run_audit.json` con:

```json
{
  "execution_mode": {
    "requested": "fast|balanced|conservative",
    "used": "fast|balanced|conservative",
    "etth_max": 3.5|6.0|10.0,
    "score_formula": "...",
    "min_strength": 0.0,
    "min_prob_win": 0.0,
    "eligible_trades": 1|4|5,
    "kept_trades": 1|4|5,
    "dropped_trades": 4|1|0,
    "reason_counts": {
      "etth": 4|1|0,
      "cap": 0,
      "strength": 0,
      "prob": 0
    },
    "exposure_before": 861.98,
    "exposure_after": 227.92|642.41|861.98,
    "exposure_cap": 800.0|null
  }
}
```

---

## REPRODUCCIÓN

### Run FAST (rotación rápida)
```bash
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan_fast.csv \
  --month 2026-01 \
  --capital 1000 \
  --exposure-cap 800 \
  --execution-mode fast \
  --asof-date 2026-01-15
```

### Run BALANCED (default)
```bash
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan_balanced.csv \
  --month 2026-01 \
  --capital 1000 \
  --exposure-cap 800 \
  --execution-mode balanced \
  --asof-date 2026-01-15
```

### Run CONSERVATIVE (máxima confianza)
```bash
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan_conservative.csv \
  --month 2026-01 \
  --capital 1000 \
  --execution-mode conservative \
  --asof-date 2026-01-15
```

### Run con filtros adicionales
```bash
# Filtro: solo trades con prob_win >= 96%
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan_filtered.csv \
  --month 2026-01 \
  --capital 1000 \
  --exposure-cap 800 \
  --execution-mode balanced \
  --min-prob-win 0.96 \
  --asof-date 2026-01-15

# Filtro: custom ETTH max en conservative
python scripts/run_trade_plan.py \
  --forecast data/daily/signals_with_gates.parquet \
  --prices data/daily/ohlcv_daily.parquet \
  --out val/trade_plan_custom.csv \
  --month 2026-01 \
  --capital 1000 \
  --execution-mode conservative \
  --etth-max 5.0 \
  --asof-date 2026-01-15
```

---

## VALIDATION CHECKLIST

- ✅ **FAST:** ETTH filter (≤3.5d) aplicado correctamente
- ✅ **FAST:** AMD única elegible, dropped 4 trades
- ✅ **BALANCED:** Score formula mixta funciona
- ✅ **BALANCED:** 4 trades con score > 0.7
- ✅ **CONSERVATIVE:** Todos 5 trades aprobados
- ✅ **CONSERVATIVE:** Orden por strength (no reordena CSV)
- ✅ **ALL:** Exposure cap respetado (si aplica)
- ✅ **ALL:** Audit JSON completo con reason_counts
- ✅ **ALL:** CSV mantiene orden original (por strength del core)

---

## PRÓXIMOS PASOS

1. **Integrar con dashboard:** Mostrar modo actual en UI
2. **A/B testing:** Comparar backtest de los 3 modos
3. **Auto-switching:** Cambiar modo según volatilidad de mercado
4. **Constraints adicionales:** min_exposure, max_duration, etc.

---

**Status:** ✅ IMPLEMENTACIÓN COMPLETA | Todos 3 modos validados (Jan 17, 2026)

