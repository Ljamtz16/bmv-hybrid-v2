# ETTH (Expected Time To Hit) - Guía Operativa

**Fecha:** 15 Enero 2026  
**Sistema:** USA_HYBRID_CLEAN_V1  
**Implementación:** Post-proceso en run_trade_plan.py (NO modifica core)

---

## 1. Qué es ETTH

**ETTH (Expected Time To Hit):** Días estimados para que el precio alcance el target (TP).

**Cálculo:**
```
ETTH = (TP_price - Entry_price) / Entry_price / ATR14%
```

Donde:
- **ATR14%** = Average True Range (14 días) como % del close
- **Clamp:** [0.5, 10] días para estabilidad
- **Método:** Post-proceso usando historial OHLCV real

**Ejemplo real (15 Enero 2026):**
```
CVX:  4.34 días (más volátil → llega más rápido)
CAT:  4.34 días
XOM:  4.74 días
WMT:  5.68 días
PFE:  6.17 días (menos volátil → tarda más)
```

---

## 2. Cómo Usarlo (Sin Cambiar Ranking Base)

### ✅ Usos Recomendados (Guía Operativa)

**A) Priorizar ejecución:**
- Ejecutar primero trades con **menor ETTH** (oportunidades más rápidas)
- Ejemplo: CVX (4.34d) antes que PFE (6.17d)

**B) Planificar rotación de capital:**
- Estimar "capital bloqueado" por trade
- Capital bloqueado ≈ exposure × ETTH / 3 días (horizonte H3)
- Ayuda a planificar cuándo tendrás capital libre

**C) Expectativas de timing:**
- Si ETTH = 4.34d → esperar ~4 días para TP
- Si no llega en 2×ETTH → considerar revisar setup

### ❌ NO Usar Todavía (Hasta 2-4 Semanas de Tracking)

**NO filtrar trades por ETTH** (aún):
- Sistema aún no tiene suficiente historial
- Podría eliminar buenos trades por ruido

**NO ajustar sizing por ETTH** (aún):
- Primero validar estabilidad

**NO usar como stop-loss temporal:**
- ETTH es expectativa, no garantía

---

## 3. Monitoreo de Estabilidad (Reglas Automáticas)

### Criterios de Confiabilidad

El sistema marca ETTH como **"no confiable"** si:

```python
# Regla 1: Sin variabilidad
etth_unique <= 1  # Todos los trades con mismo ETTH

# Regla 2: Demasiados NaN
etth_nan_pct > 20%  # >20% de trades sin ETTH

# Regla 3: Degraded flags
etth_degraded_count > 50%  # >50% trades con ATR14 faltante
```

**Acción si NO confiable:**
- ⚠️ Warning en audit log: `etth_global_warning`
- Usar ETTH solo como referencia, NO para decisiones
- Revisar por qué falta historial (ticker nuevo, data gaps)

### Audit Log Completo

Cada ejecución guarda:
```json
{
  "etth_method": "atr14_proxy",
  "etth_window": 14,
  "etth_clamp_min": 0.5,
  "etth_clamp_max": 10.0,
  "etth_n": 5,
  "etth_nan_pct": 0.0,
  "etth_unique": 5,
  "etth_mean": 5.06,
  "etth_min": 4.34,
  "etth_max": 6.17,
  "etth_degraded_count": 0,
  "atr14_pct_mean": 0.0196,
  "atr14_pct_nan_pct": 0.0,
  "etth_global_warning": null  // o mensaje si degradado
}
```

---

## 4. Output Diario (Resumen Operativo)

El wrapper genera resumen con orden sugerido:

```
=== RESUMEN DIARIO ===
Trades:           5
BUY/SELL:         5 BUY, 0 SELL
Prob Win (mean):  92.86%
Exposure (total): $99,174.36
ETTH (mean):      5.06 dias
ETTH (range):     4.34 - 6.17 dias

Detalles por trade (ordenado por ETTH):
  CVX    | BUY  | $19,871.81 | prob=96.0% | etth=4.34d  ← ejecutar primero
  CAT    | BUY  | $19,542.45 | prob=91.0% | etth=4.34d
  XOM    | BUY  | $19,873.17 | prob=96.3% | etth=4.74d
  WMT    | BUY  | $19,895.10 | prob=92.6% | etth=5.68d
  PFE    | BUY  | $19,991.83 | prob=88.4% | etth=6.17d  ← ejecutar último
```

---

## 5. Checklist de Validación (Pre-Operación)

Antes de usar ETTH para decisiones, verificar:

- [ ] `etth_unique` > 1 (hay variabilidad)
- [ ] `etth_nan_pct` < 20% (datos suficientes)
- [ ] `etth_degraded_count` = 0 o mínimo
- [ ] No hay `etth_global_warning` en audit
- [ ] Rango ETTH razonable (típicamente 2-8 días para H3)

**Si falla alguno:**
- ⚠️ ETTH informativo, pero NO usar para decisiones
- Investigar: ¿tickers nuevos? ¿data gaps? ¿ATR14 faltante?

---

## 6. Roadmap de Uso (Gradual)

### Semanas 1-2 (ACTUAL)
- ✅ Solo información (no afecta decisiones)
- ✅ Monitorear estabilidad
- ✅ Comparar ETTH predicho vs tiempo real

### Semanas 3-4
- Validar precisión: ¿ETTH ≈ tiempo real al TP?
- Ajustar parámetros (window, clamp) si necesario

### Mes 2+
- Considerar filtrado: descartar trades con ETTH > 8d si underperforman
- Ajustar sizing: trades con ETTH bajo → mayor allocation

### Mes 3+
- Modelo ML para ETTH (reemplazar proxy ATR14)
- Integrar ETTH en score de ranking

---

## 7. Troubleshooting

**Problema:** ETTH todos iguales (etth_unique = 1)
- **Causa:** ATR14 muy similar entre tickers
- **Fix:** Validar que prices tiene historial real (no sintético)

**Problema:** etth_nan_pct alto
- **Causa:** Tickers sin historial suficiente (<14 días)
- **Fix:** Aumentar universo de tickers con más historia

**Problema:** etth_degraded alto
- **Causa:** Gaps en OHLCV (high/low/close faltantes)
- **Fix:** Revisar data quality en 00_download.py

**Problema:** ETTH predicho ≠ real
- **Causa:** Proxy ATR14 no suficiente
- **Fix:** Reemplazar con modelo ML (scripts/39_predict_time_to_hit.py)

---

## 8. Referencias Técnicas

**Implementación:** [scripts/run_trade_plan.py](scripts/run_trade_plan.py#L17-L126)  
**Funciones:**
- `compute_atr14_pct()` - Calcula ATR14 desde historial
- `add_etth_days_to_trade_plan()` - Post-proceso ETTH
- Integración no invasiva: no modifica 33_make_trade_plan.py

**Documentos relacionados:**
- TECHNICAL_DEBT.md - Issues arquitectónicos
- VALIDACIONES_FINALES.md - Pre-E2E validations
- checklist_60s.py - Validación automática ETTH

---

**Última actualización:** 15 Enero 2026, 18:00 CDMX  
**Status:** ✅ OPERACIONAL (post-proceso, no afecta core)
