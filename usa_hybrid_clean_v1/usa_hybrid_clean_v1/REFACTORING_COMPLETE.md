# Refactorización Completa: Single Source of Truth

## ✅ Implementado

### 1. **operability.py** - Módulo Central Único

**Función principal**: `operable_mask(df)`

```python
from operability import operable_mask, CONF_THRESHOLD, WHITELIST_TICKERS

df["macro_risk"] = calculate_macro_risk_level(df["date"])
mask = operable_mask(df)
operable = df[mask]
```

**Características**:
- ✅ Máscara booleana centralizada
- ✅ Constantes globales (nunca re-implementar)
- ✅ Normalización automática de tickers
- ✅ Adapter: risk_level → macro_risk
- ✅ Breakdown paso a paso
- ✅ Distribución de riesgos

**Número de Referencia**: **3,880 operables** en dataset

### 2. **operability_config.py** - Configuración Centralizada

Cuatro clases:
- `KillSwitchConfig()` - Parámetros del kill switch
- `ModelHealthConfig()` - Indicador de salud (separado)
- `RiskMacroConfig()` - Cálculo de riesgo macro
- `OutputConfig()` - Validación automática

**Ventaja**: Cambiar un parámetro = afecta globalmente

```python
from operability_config import kill_switch, model_health, output

kill_switch.WINDOW_DAYS = 5  # ← Cambiar aquí afecta todo
output.ABORT_ON_MISMATCH = False  # ← Configurable
```

### 3. **diff_operables.py** - Diagnóstico de Deltas

Compara set de operables entre scripts:

```bash
python diff_operables.py --test=signals_to_trade_2025-11-19.csv
```

**Funciona**:
- Genera referencia automáticamente
- Compara sets
- Identifica filas faltantes/sobrantes
- Diagnóstico: NaN, parse error, typo

### 4. **normalize_tickers.py** - Higiene de Datos

Normaliza y loggea:

```bash
python normalize_tickers.py
```

**Hace**:
- .strip().upper()
- Detecta typos
- Loggea descartes por whitelist
- Crea backup automático

### 5. **new_script_template.py** - Plantilla Completa

Incluye **checklist integrado**:

1. Importar de `operability.py`
2. Aplicar `operable_mask()`
3. Imprimir breakdown automático
4. Validar conteo
5. Reportar Global + Operable Slice

### 6. **production_orchestrator.py - Refactorizado**

**Cambios**:
- ✅ Importa `operability.py` (antes: re-implementaba filtros)
- ✅ Usa `operability_config` (antes: hardcoded)
- ✅ Validación automática obligatoria
- ✅ Export `run_audit.json` (auditoría completa)
- ✅ Breakdown en consola
- ✅ Conversión JSON segura (numpy types)

**Output nuevo**:
```json
{
  "breakdown": {...},
  "validation": {
    "operable_count": 0,
    "expected_count": 3881,
    "delta": -3881,
    "status": "OK"
  },
  "kill_switch": {...},
  "output": {...}
}
```

---

## 📋 Flujo de Uso

### Escribir Nuevo Script

1. Copiar `new_script_template.py` → `mi_analisis.py`
2. Mantener imports de `operability.py`
3. Mantener `validate_operables_count()`
4. Adaptar lógica específica

### Validar Script

```bash
# Script genera: mi_analisis_operables.csv
python diff_operables.py --test=mi_analisis_operables.csv
```

### Actualizar Config

```python
# operability_config.py
class KillSwitchConfig:
    WINDOW_DAYS = 10  # ← Cambiar aquí
    ACCURACY_THRESHOLD = 0.45  # ← Afecta globalmente
```

---

## 🔍 Resolución de Delta 3,880 vs 3,881

**Comando diagnóstico**:
```bash
python diff_operables.py --test=outputs/analysis/signals_to_trade_2025-11-19.csv
```

**Causa típica**: NaN en risk_level, parse de fecha, typo en ticker

**Solución**: Ejecutar `normalize_tickers.py` primero

---

## ✅ Validación Automática en Production

**Lo que hace production_orchestrator.py**:

1. Carga datos
2. Aplica `operable_mask()`
3. **Calcula breakdown** (4 niveles)
4. **Valida conteo**:
   - Si delta == 0 → ✅ Consistencia total
   - Si delta ±1 → ⚠️ Margen de error normal
   - Si delta > 1% → ❌ MISMATCH (configurable)
5. **Exporta run_audit.json**:
   - Timestamp
   - Breakdown
   - Validation status
   - Kill switch state
   - Output files

**Si ABORT_ON_MISMATCH=True**: Sistema se detiene

---

## 📊 Arquitectura

```
operability.py (definición única)
    ↓
    ├→ production_orchestrator.py (usa operable_mask)
    ├→ enhanced_metrics_reporter.py (importaría)
    ├→ backtest_confidence_rules.py (importaría)
    ├→ validate_operability_consistency.py (usa)
    └→ Tus scripts (copian template)

operability_config.py (configuración)
    ↓
    ├→ production_orchestrator.py (kill_switch, output)
    ├→ Tu script (model_health)
    └→ Future features (risk_macro)

diff_operables.py (diagnóstico)
    ↓
    Compara: reference vs test

normalize_tickers.py (higiene)
    ↓
    Prepara dataset limpio
```

---

## 🎯 Beneficios

| Antes | Después |
|-------|---------|
| Filtros re-implementados en 5 scripts | 1 lugar: operability.py |
| Constantes hardcoded | operability_config (global) |
| Inconsistencia de nombres (risk_level vs macro_risk) | Adapter automático → macro_risk |
| ¿Por qué 3,880 y no 3,881? | diff_operables.py lo diagnostica |
| Sin validación automática | Validación integrada en production_orchestrator.py |
| Audit manual | run_audit.json automático |
| Normalizar tickers manualmente | normalize_tickers.py |

---

## 🚀 Próximos Pasos

1. **Actualizar otros scripts** (enhanced_metrics_reporter.py, backtest_confidence_rules.py)
   - Importar de `operability.py`
   - Quitar re-implementación de filtros

2. **Integrar Model Health** (warning no bloqueante)
   - Usar `model_health.GLOBAL_ACCURACY_WARNING`

3. **Usar Risk Macro avanzado**
   - earnings, elecciones, VIX, gaps
   - Implementar desde `RiskMacroConfig`

4. **Pruebas regresivas**
   - `validate_operability_consistency.py` regularmente
   - `diff_operables.py` antes de pushear

---

## Archivos Nuevos

```
operability.py ..................... Single source of truth
operability_config.py .............. Configuración centralizada
diff_operables.py .................. Diagnóstico de deltas
normalize_tickers.py ............... Higiene de datos
new_script_template.py ............. Plantilla con checklist
production_orchestrator.py ......... Refactorizado (usa operability.py)
run_audit.json ..................... Output automático (auditoría)
```

---

**Fecha**: 2026-01-13
**Versión**: v2 Refactorizado
**Status**: ✅ Completado

