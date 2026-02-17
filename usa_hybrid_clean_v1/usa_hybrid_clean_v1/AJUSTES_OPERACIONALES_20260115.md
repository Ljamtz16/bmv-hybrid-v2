# ✅ Ajustes Operacionales Implementados - 15 Enero 2026

**Timestamp:** 2026-01-15 19:00 CDMX  
**Status:** ✅ COMPLETADO Y VALIDADO

---

## Resumen

Se implementaron dos ajustes operacionales recomendados para blindar el sistema antes de E2E:

1. **A) Warning "side" accionable** - Detectar e imputar columna faltante
2. **B) Guardrail de exposure** - Alertar si exposición > 98% del capital

Ambos mejoran la transparencia y previenen sorpresas operacionales sin cambiar la lógica core.

---

## Ajuste A: Warning "side" Accionable

### Problema Original
```
[WARN] Columnas opcionales FALTANTES: ['side']
```
- Warning sin contexto (¿qué se hizo al respecto?)
- No trazable en audit log

### Solución Implementada

**En `scripts/run_trade_plan.py`:**

1. **Función `validate_forecast_schema()`** (línea 136-147)
   - Retorna dict con `missing_optional` en lugar de solo imprimir
   - Permite tracking de qué columnas faltaron

2. **Función `prepare_forecast_csv()`** (línea 149-176)
   - **Detecta:** si 'side' falta en forecast
   - **Imputación:** `BUY` si `prob_win > 0.5`, `SELL` si ≤ 0.5
   - **Output:** mensaje informativo `[INFO] Imputando columna 'side'...`
   - **Retorna:** `(df, validation)` para trazabilidad

3. **Audit Log** (línea 307-313)
   - Nuevo dict `forecast_issues`:
     ```json
     {
       "missing_optional_cols": ["side"],
       "side_imputed": true,
       "side_imputation_rule": "BUY if prob_win > 0.5 else SELL"
     }
     ```

### Validación

**Ejemplo de audit log actualizado:**
```json
{
  "forecast_issues": {
    "missing_optional_cols": ["side"],
    "side_imputed": true,
    "side_imputation_rule": "BUY if prob_win > 0.5 else SELL"
  },
  ...
}
```

**Output esperado en consola:**
```
[WARN] Columnas opcionales FALTANTES: ['side']
[INFO] Imputando columna 'side' basada en prob_win > 0.5
[OK] Forecast preparado: data/daily/forecast_temp_for_33.csv
```

**Resultado:** Warning es "accionable" - quién lea el audit sabe exactamente qué sucedió.

---

## Ajuste B: Guardrail de Exposure

### Problema Original
Sin guardrail explícito, cambios de redondeos podrían:
- Exceder 100% de capital (insufficient buying power)
- No ser detectados hasta runtime del broker

### Solución Implementada

**En `pre_e2e_final_check.py` (línea 161-194):**

1. **Storage en audit log**
   - `scripts/run_trade_plan.py` calcula `exposure_total = sum(qty × entry)` (línea 352)
   - Guardado en audit: `audit["exposure_total"] = float(...)` (línea 352)

2. **Validación en pre_e2e_final_check** (Check 5)
   ```python
   if 'exposure_total' in audit:
       exposure = audit['exposure_total']
       capital = audit.get('capital', 100000)
       exposure_pct = (exposure / capital) * 100
       
       # Verificar negativos y NaNs en qty/entry
       # CRITICO: if exposure_pct > 100.0 → issues.append()
       # WARN: elif exposure_pct > 98.0 → print warning
   ```

3. **Criterios**
   - 🔴 **ERROR:** `exposure_pct > 100.0` → FALLA pre_e2e (capital insuficiente)
   - 🟡 **WARN:** `exposure_pct > 98.0` → PASS pero advierte cambios de redondeo
   - 🟢 **OK:** `exposure_pct ≤ 98.0` → Sin riesgos

### Validación

**Output de prueba (exposure = $99,174.36 / $100,000):**
```
[WARN] Exposure alta (guardrail): 99.17% > 98%
       Disponible: $825.64 (0.83%)
       Riesgo: cambios de redondeo pueden exceder 100%

  OK Todas las validaciones PASS
```

**Resultado:** Operador es alerta que tiene margen pequeño (0.83%) para cambios.

---

## Verificación Completa

### Test ejecutado (2026-01-15 19:03 CDMX)

```bash
$ python pre_e2e_final_check.py
```

**Output relevante:**
```
[PASO 2/4] Generando trade plan fresco (T-1)...
[WARN] Columnas opcionales FALTANTES: ['side']
[INFO] Imputando columna 'side' basada en prob_win > 0.5

[PASO 3/4] Validando output generado...
[WARN] Exposure alta (guardrail): 99.17% > 98%
       Disponible: $825.64 (0.83%)
       Riesgo: cambios de redondeo pueden exceder 100%

STATUS: LISTO PARA E2E MANANA 14:30 CDMX
```

### Audit log ejemplo

```json
{
  "exposure_total": 99174.3600654602,
  "capital": 100000.0,
  "forecast_issues": {
    "missing_optional_cols": ["side"],
    "side_imputed": true,
    "side_imputation_rule": "BUY if prob_win > 0.5 else SELL"
  }
}
```

---

## Impacto

| Aspecto | Antes | Después |
|---------|-------|---------|
| Warning "side" | Ruido sin contexto | Accionable + trazable en audit |
| Detección exposure >100% | Manual/sorpresa | Automática en pre_e2e_final_check |
| Exposición margin buffer | Sin alertas | Guardrail suave >98% |
| Auditabilidad | Parcial | Completa (qué columnas imputadas, por qué regla) |

---

## Próximas Acciones

### Pre-E2E Mañana (14:25)
```bash
python pre_e2e_final_check.py
```

**Checklist:**
- ✅ PASO 1: Checklist 60s inicial
- ✅ PASO 2: Trade plan (verifica warning side si aplica)
- ✅ PASO 3: Validaciones (incluye guardrail exposure)
- ✅ PASO 4: Checklist 60s final

### Si WARN de exposure > 98%
- **Opción 1:** Reducir max_open (menos trades)
- **Opción 2:** Aumentar capital (por simulación)
- **Opción 3:** Usar como está (normal para H3 agresivo)

### Si ERROR de exposure > 100%
- **ACCION:** Revisar redondeos en qty/entry
- **Root cause:** Likely floating point precision
- **Fix:** Usar `decimal.Decimal` (2-3 horas)

---

## Referencias

- [scripts/run_trade_plan.py](scripts/run_trade_plan.py) - Líneas 136-176 (imputación side)
- [scripts/run_trade_plan.py](scripts/run_trade_plan.py) - Línea 352 (guardar exposure_total)
- [pre_e2e_final_check.py](pre_e2e_final_check.py) - Línea 161-194 (validación exposure)
- [ETTH_OPERATIONAL_GUIDE.md](ETTH_OPERATIONAL_GUIDE.md) - Context operativo

---

**Status:** ✅ BLINDAJE OPERACIONAL COMPLETO

