# Ensure-One Mechanism - Guía de Uso

## Resumen
El flag `--ensure-one` fuerza **al menos 1 trade** cuando el plan queda vacío tras aplicar filtros estrictos, usando umbrales de fallback más relajados pero manteniendo E[PnL]>0 y guardrails de capital.

## Caso de Uso
- **Paper trading**: Asegurar actividad diaria para recolectar métricas
- **Validación**: Garantizar datos suficientes para análisis estadístico
- **Testing**: Verificar pipeline end-to-end con exposures controlados

## Parámetros

### Obligatorio
- `--ensure-one`: Activa el mecanismo de fallback

### Exposure del trade forzado
- `--ensure-exposure-min <usd>`: Mínimo exposure (default: 500)
- `--ensure-exposure-max <usd>`: Máximo exposure (default: 600)

### Filtros de fallback (más laxos que los normales)
- `--fallback-prob-min <float>`: Probabilidad mínima (default: 0.20 vs 0.25 normal)
- `--fallback-ptpmin <float>`: P(TP<SL) mínimo (default: 0.15 vs 0.18-0.20 normal)
- `--fallback-etth-max <float>`: ETTH máximo en días (default: 0.30 vs 0.25 normal)
- `--fallback-cost <float>`: Costo implícito para E[PnL] (default: 0.0003 vs 0.0005 normal)

## Uso Básico

### Con configuración default
```powershell
python scripts\40_make_trade_plan_intraday.py --date 2025-10-31 `
  --tp-pct 0.028 --sl-pct 0.005 `
  --per-trade-cash 250 --capital-max 1000 `
  --allow-fractional --min-qty 0.01 `
  --ensure-one
```

### Con umbrales personalizados
```powershell
python scripts\40_make_trade_plan_intraday.py --date 2025-10-31 `
  --tp-pct 0.028 --sl-pct 0.005 `
  --per-trade-cash 250 --capital-max 1000 `
  --allow-fractional --min-qty 0.01 `
  --ensure-one `
  --ensure-exposure-min 500 --ensure-exposure-max 600 `
  --fallback-prob-min 0.18 --fallback-ptpmin 0.12 `
  --fallback-etth-max 0.35 --fallback-cost 0.0002
```

## Comportamiento

### Condiciones de activación
1. Plan queda vacío tras aplicar filtros normales + guardrails
2. Flag `--ensure-one` está activado

### Proceso de fallback
1. Toma forecast original (pre-filtros)
2. Recalcula E[PnL] con `--fallback-cost` (más bajo = más flexible)
3. Aplica filtros de fallback (prob, P(TP<SL), ETTH, E[PnL]>0)
4. Rankea por eficiencia temporal (E[PnL]/ETTH)
5. Selecciona el mejor candidato
6. Calcula qty para alcanzar exposure en [min, max]
7. Respeta `capital_max` y límites de guardrails

### Garantías
- ✅ Exposure SIEMPRE en rango [min, max]
- ✅ E[PnL] > 0 (nunca fuerza trades perdedores)
- ✅ Respeta `capital_max` global
- ✅ Usa qty fraccional si `--allow-fractional` está activo
- ✅ Mantiene guardrails de sector y ticker

### Casos edge
- **Sin candidatos válidos con E[PnL]>0**: No fuerza trade, plan queda vacío
- **Precio > ensure-exposure-max**: Qty será < 1, requiere `--allow-fractional`
- **Capital insuficiente**: Ajusta exposure a capital disponible (nunca excede `capital_max`)

## Ejemplo Real (2025-10-22)

### Configuración
- Filtros normales: prob_min=0.90, p_tp_sl_min=0.60 (muy restrictivos)
- Fallback: prob_min=0.20, p_tp_min=0.15, etth_max=0.30d, cost=0.0003
- Exposure target: $500-$600

### Resultado
```
[plan_intraday] FALLBACK: Activando ensure-one (plan vacío)
  Candidatos fallback (E[PnL]>0, prob≥0.2, P(TP<SL)≥0.15, ETTH≤0.3d): 2
  ✅ Fallback: AMD LONG @ $227.45, qty=2.1983, exposure=$500.00
  
Plan final: 1 trades
Exposure total: $500
Prob win media: 30.6%
ETTH media: 0.19 días
```

## Recomendaciones

### Paper Trading (actual)
```yaml
--ensure-one
--ensure-exposure-min 500
--ensure-exposure-max 600
--fallback-prob-min 0.20
--fallback-ptpmin 0.15
--fallback-etth-max 0.30
--fallback-cost 0.0003
```

### Live Trading
**⚠️ NO USAR `--ensure-one` en producción**
- Forzar trades artificialmente introduce sesgos
- Mejor aceptar días sin señales
- Si se usa, subir umbrales de fallback:
  - prob_min ≥ 0.35
  - p_tp_min ≥ 0.20
  - cost ≥ 0.0005

## Integración con Validador

El validador `validate_pipeline_intraday.py` NO propaga flags de ensure-one automáticamente. Para usar fallback, ejecutar step 40 manualmente:

```powershell
# 1) Ejecutar pipeline normal
python scripts\validate_pipeline_intraday.py --date 2025-10-31 --prob-min 0.25

# 2) Si plan vacío, re-ejecutar step 40 con ensure-one
python scripts\40_make_trade_plan_intraday.py --date 2025-10-31 `
  --tp-pct 0.028 --sl-pct 0.005 `
  --per-trade-cash 250 --capital-max 1000 `
  --allow-fractional --min-qty 0.01 `
  --ensure-one --ensure-exposure-min 500 --ensure-exposure-max 600
```

## Debugging

Ver en terminal:
```
[plan_intraday] FALLBACK: Activando ensure-one (plan vacío)
  Candidatos fallback (E[PnL]>0, prob≥X, P(TP<SL)≥Y, ETTH≤Zd): N
  ✅ Fallback: <TICKER> <DIR> @ $<PRICE>, qty=<QTY>, exposure=$<EXP>
```

Ver en `plan_stats.json`:
```json
{
  "num_plan_trades": 1,
  "exposure_total": 500.00,
  "prob_win_mean": 0.306,
  ...
}
```

Ver en `trade_plan_intraday.csv`:
- Columna `qty`: Cantidad (fraccional si --allow-fractional)
- Columna `exposure`: Exposure real en USD
