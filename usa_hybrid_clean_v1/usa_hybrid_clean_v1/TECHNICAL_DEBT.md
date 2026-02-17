# 📋 TECHNICAL DEBT REGISTRY

**Sistema:** USA_HYBRID_CLEAN_V1 (H3 multidía)  
**Actualizado:** 15 Enero 2026, 18:00 CDMX  
**Status:** 4 issues identificados, 2 resueltos, 2 mitigados

**Pre-E2E Status:** ✅ LISTO (todos los issues críticos resueltos/mitigados)

---

## Issue #1: Encoding (Unicode Characters) — MITIGATED ⚠️

**Prioridad:** 🔴 CRÍTICO (puede romper en producción)  
**Status:** ⚠️ Mitigado por runner + **MUST-FIX antes de delegar**

### Problema
Scripts `11_infer_and_gate.py` y `33_make_trade_plan.py` usan caracteres unicode (→, ✅, ❌) en prints.

Sin `$env:PYTHONIOENCODING='utf-8'`:
```
UnicodeEncodeError: 'utf-8' codec can't decode byte 0xf3...
```

### Solución Actual
✅ `$env:PYTHONIOENCODING='utf-8'` en runners (.ps1)

**PERO:** Dependiente del runner. Si un operador ejecuta scripts manualmente, ROMPE.

### Solución Ideal (15 minutos)
Cambiar unicode a ASCII en los scripts:
```python
# Cambiar: print("→ Computando...")
# Por:     print("-> Computando...")
```

**Status:** ⚠️ Mitigado por costumbre, NO por código  
**Riesgo si no se arregla:** Alto — rompe en terminal sin UTF-8  
**⚠️ MUST-FIX ANTES DE DELEGAR A TERCEROS**

---

## Issue #2: y_hat Semántica Incorrecta — FIXED ✅

**Prioridad:** 🔴 CRÍTICO (lógica incorre cta en production)  
**Status:** ✅ **RESUELTO (15 Enero 13:00 CDMX)**

### Problema (Detectado)
- `11_infer_and_gate.py` NO genera `y_hat`
- `33_make_trade_plan.py` lo requería
- Fue agregado como "copia de prob_win" (INCORRECTO)
- Se usaba para dirección y ranking

**Error semántico:**
- `prob_win` = probabilidad de ganancia (0-1)  
- `y_hat` debería ser = retorno esperado, pero NO existe

### Fix Implementado

**File: scripts/33_make_trade_plan.py**

```python
# Antes (INCORRECTO):
f["side"] = f["y_hat"].apply(lambda v: "BUY" if v >= 0 else "SELL")
f["strength"] = f["prob_win"] * f["y_hat"].abs()

# Después (CORRECTO):
f["side"] = f["prob_win"].apply(lambda v: "BUY" if v > 0.5 else "SELL")
f["strength"] = f["prob_win"]  # Directo, sin y_hat fake
```

**Validación:** ✅ strength == prob_win en output

---

## Issue #3: sklearn/joblib Version Mismatch — MITIGATED ⚠️

**Prioridad:** 🟠 ALTO (puede fallar inesperadamente)  
**Status:** ⚠️ Mitigación pragmática: Alinear runtime a 1.7.2

### Problema REAL (verificado 15 Enero 13:14 CDMX)
```
Modelos entrenados: sklearn 1.7.2 (10 Nov 2025)
Runtime actual:     sklearn 1.7.1

Warning al cargar:
  InconsistentVersionWarning: Trying to unpickle estimator 
  from version 1.7.2 when using version 1.7.1
```

**Riesgo:** Mediano — puede romper con cambios menores en pipelines de árboles/estimators

### Solución Pragmática RECOMENDADA (5 minutos)
**Subir runtime a 1.7.2** para empatar con modelos:
```bash
pip install scikit-learn==1.7.2
python verify_versions.py  # Verificar match
```

Más rápido que reentrenar (120+ min), sin pérdida de funcionalidad.

### Mitigación Actual
✅ **requirements_locked.txt** actualizado:
```
scikit-learn==1.7.2  ← Alineado con modelos
joblib==1.5.1
numpy==2.1.3
pandas==2.2.3
xgboost==3.1.1
catboost==1.2.8
```

✅ **Script de verificación:** `verify_versions.py`

**Single Source of Truth:** `requirements_locked.txt`

---

## Issue #4: Parquet/CSV Format Mismatch — FIXED ✅

**Prioridad:** 🟡 MEDIO  
**Status:** ✅ **RESUELTO (15 Enero 13:00 CDMX)**

### Problema
```
11_infer → parquet
33_make_trade ← CSV (esperaba)
```

### Solución Implementada

✅ **scripts/run_trade_plan.py** — Wrapper que:
- Auto-detecta CSV o Parquet
- Valida schema
- Convierte si es necesario
- Genera audit log JSON

✅ **run_trade_plan.ps1** — Runner PowerShell

**Uso:**
```powershell
.\run_trade_plan.ps1 `
  -Forecast data/daily/signals_with_gates.parquet `
  -Prices data/daily/ohlcv_daily.parquet `
  -Out val/trade_plan.csv
```

---

## Resumen Ejecutivo

| Issue | Prioridad | Status | Fix Time | Risk |
|-------|-----------|--------|----------|------|
| **1. Encoding** | 🔴 | ⚠️ Mitig. | 15 min | Alto |
| **2. y_hat** | 🔴 | ✅ **FIXED** | Done | Crítico |
| **3. sklearn** | 🟠 | ⚠️ Cong. | 120 min | Medio |
| **4. Parquet** | 🟡 | ✅ **FIXED** | Done | Bajo |

---

## Plan Remediación

### Hoy (Antes E2E)
```
✅ Issue #2: RESUELTO
✅ Issue #4: RESUELTO
⚠️ Issue #1: Mitigado (UTF-8 env var)
⚠️ Issue #3: Congelado (requirements_frozen.txt)
```

### Próxima semana (Recomendado)
```
Issue #1: Cambiar unicode → ASCII (~15 min)
Issue #3: Crear environment_locked.yaml
```

---

**Recomendación:** E2E_TEST_PROCEDURE.md mañana 14:30 CDMX está **GO**.



### Problema

Scripts imprimen caracteres no-ASCII (flechas `→`, unicode `✅`, etc.) que causan:
```
UnicodeEncodeError: 'utf-8' codec can't decode byte 0xf3 in position 20
```

### Contexto

**Afectados:**
- scripts/11_infer_and_gate.py (múltiples prints con `→`, `✅`)
- scripts/33_make_trade_plan.py (múltiples prints con unicode)

**Workaround Actual:**
```powershell
$env:PYTHONIOENCODING='utf-8'
python .\scripts\33_make_trade_plan.py ...
```

**Riesgo:**
- Un operador que ejecute SIN esa variable de entorno → **SCRIPT ROMPE**
- No es error silencioso, es total failure
- Producción sin esa variable configurada = fallo

### Soluciones Recomendadas

#### OPCION A: Incluir en .ps1 runner (MÍNIMO)

En `run_h3_daily.ps1`, agregar al inicio:
```powershell
$env:PYTHONIOENCODING='utf-8'
```

**Tiempo:** 2 minutos  
**Riesgo:** Bajo  
**Beneficio:** 100% de cobertura si se usa runner

---

#### OPCION B: Fix en scripts (MEJOR)

Reemplazar caracteres non-ASCII en prints:

**Antes:**
```python
print("[✅] 8 señales válidas tras gates")
print(f"low_vol: 4/9 señales (threshold=0.6) → PASS")
```

**Después:**
```python
print("[OK] 8 señales válidas tras gates")
print(f"low_vol: 4/9 señales (threshold=0.6) PASS")
```

**Scripts a Revisar:**
```
scripts/11_infer_and_gate.py    (líneas con →, ✅)
scripts/33_make_trade_plan.py   (líneas con →, ✅)
scripts/20_*.py                  (probablemente)
scripts/24_*.py                  (probablemente)
```

**Tiempo:** 30-45 minutos (verificar todos los scripts)  
**Riesgo:** Bajo (solo cambios de texto)  
**Beneficio:** Portabilidad total (funciona sin env vars)

---

## 2. SKLEARN VERSION MISMATCH (CRÍTICO a MEDIANO PLAZO)

### Problema

```
InconsistentVersionWarning: 
  Estimator RF was fitted with version 1.7.2 
  but version 1.7.1 is installed
```

**Modelos afectados:** RF, XGB, CAT, META (4 modelos joblib)

### Por Qué Es Crítico

Con joblib + scikit-learn version mismatch:

1. **Hoy:** Funciona (backward compatible por ahora)
2. **Futuro:** Puede explotar sin warning (cambios intenos joblib)
3. **Producción:** Comportamiento no reproducible entre máquinas

**Riesgo Real:**
```
- Model A (1.7.2 joblib): genera señal X
- Model B (1.7.1 joblib): genera señal Y (diferente)
- Result: Predictions divergentes entre runs
```

### Soluciones

#### OPCION A: Congelar Versiones (INMEDIATO)

```bash
# Generar requirements.txt actual
pip freeze > requirements.txt

# Asegurar en requirements.txt:
scikit-learn==1.7.1
joblib==1.4.2
xgboost==2.0.3
catboost==1.2.2
```

**Ventaja:** Garantiza reproducibilidad  
**Desventaja:** Requiere que todos corran con esas versiones  
**Tiempo:** 5 minutos  
**Prioridad:** 🔴 ALTA (hacer HOY si posible)

---

#### OPCION B: Reentrenar Modelos (MEJOR pero 2+ horas)

Volver a entrenar y exportar bajo sklearn 1.7.1:

```python
# En 10_train_direction_ensemble_WALKFORWARD.py
# Cambiar al inicio:
from sklearn import __version__
assert __version__ == "1.7.1", f"sklearn must be 1.7.1, got {__version__}"

# Reentrenar:
python .\scripts\10_train_direction_ensemble_WALKFORWARD.py
# Esto exporta nuevos modelos con sklearn 1.7.1 embedded
```

**Ventaja:** Modelos garantizados compatibles  
**Desventaja:** 2-3 horas reentrenamiento (full walk-forward)  
**Tiempo:** 120-180 minutos  
**Prioridad:** 🟡 MEDIA (después de congelar versiones)

---

## 3. PARQUET ↔ CSV CONVERSION (TECHNICAL DEBT)

### Problema

Script 33_make_trade_plan.py espera CSV, pero datos vienen en Parquet.

**Solución Actual (Workaround):**
```
3 scripts manuales:
  - convert_parquet_to_csv.py
  - add_y_hat.py
  - convert_ohlcv_to_csv.py
```

**Riesgo:**
- Si se ejecuta 33_make_trade_plan sin conversión previa → ERROR
- Archivos CSV intermedios no están en `.gitignore` → clutter
- Si alguien actualiza el parquet, CSV se desincroniza

### Soluciones

#### OPCION A: Integrar en Pre-Processor (MEJOR)

Crear script `scripts/32_prepare_for_trade_plan.py`:

```python
#!/usr/bin/env python3
"""
32_prepare_for_trade_plan.py
Convierte outputs de 11_infer_and_gate.py a formato requerido por 33_make_trade_plan.py
"""

import pandas as pd

def prepare():
    # Parquet → CSV
    signals = pd.read_parquet("data/daily/signals_with_gates.parquet")
    signals['y_hat'] = signals['prob_win']  # Add missing column
    signals.to_csv("data/daily/signals_with_gates.csv", index=False)
    
    # Parquet → CSV
    prices = pd.read_parquet("data/daily/ohlcv_daily.parquet")
    prices['date'] = prices['date'].astype(str)
    prices.to_csv("data/daily/ohlcv_daily.csv", index=False)
    
    print("[OK] Preparado para 33_make_trade_plan.py")

if __name__ == "__main__":
    prepare()
```

Luego en runner:
```powershell
python .\scripts\11_infer_and_gate.py
python .\scripts\32_prepare_for_trade_plan.py  # ← NUEVO
python .\scripts\33_make_trade_plan.py ...
```

**Tiempo:** 30 minutos  
**Beneficio:** Automático, documentado, reutilizable  
**Prioridad:** 🟡 MEDIA

---

#### OPCION B: Actualizar 33 para aceptar Parquet (MEJOR PERO MÁS TRABAJO)

Modificar `scripts/33_make_trade_plan.py`:

```python
def load_forecast(path: str) -> pd.DataFrame:
    if path.endswith('.parquet'):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    
    # Agregar y_hat si no existe
    if 'y_hat' not in df.columns and 'prob_win' in df.columns:
        df['y_hat'] = df['prob_win']
    
    return df
```

**Tiempo:** 45 minutos (con tests)  
**Beneficio:** Flexible, sin conversiones intermedias  
**Prioridad:** 🟡 MEDIA (después de Opción A)

---

## 4. PRIORITY MATRIX

| Issue | Impact | Effort | Priority | Owner | Deadline |
|-------|--------|--------|----------|-------|----------|
| Encoding (Issue #1) | 🔴 BLOCKER | 🟢 2 min | 🔴 TODAY | DevOps | Antes E2E |
| sklearn mismatch | 🟡 MEDIUM | 🟢 5 min (A) | 🟡 SOON | ML | Esta semana |
| Parquet→CSV | 🟡 MEDIUM | 🟠 30 min | 🟡 SOON | Backend | Sprint 2 |

---

## 5. ACTION ITEMS

### TODAY (15 Enero, antes 14:30 CDMX)

```
[ ] #1: Revisar todos los print() con unicode en scripts/11 y 33
        Opción A: Agregar $env:PYTHONIOENCODING='utf-8' a run_h3_daily.ps1
        Opción B: Cambiar caracteres non-ASCII a ASCII
        
[ ] #2: Crear requirements.txt con versiones congeladas
        pip freeze > requirements.txt
        Confirmar: scikit-learn==1.7.1
```

### MAÑANA (16 Enero, después E2E)

```
[ ] #3: Crear scripts/32_prepare_for_trade_plan.py (pre-processor)
        O: Actualizar scripts/33_make_trade_plan.py para aceptar Parquet

[ ] #4: Considerar reentrenamiento si sklearn divergence causa problemas
```

---

## 📋 ARCHIVOS REFERENCIADOS

- [VALIDACION_PIPELINE_COMPLETO.md](VALIDACION_PIPELINE_COMPLETO.md)
- [run_h3_daily.ps1](run_h3_daily.ps1) — Agregar $env:PYTHONIOENCODING
- [scripts/11_infer_and_gate.py](scripts/11_infer_and_gate.py) — Revisar prints
- [scripts/33_make_trade_plan.py](scripts/33_make_trade_plan.py) — Revisar prints
- [scripts/10_train_direction_ensemble_WALKFORWARD.py](scripts/10_train_direction_ensemble_WALKFORWARD.py) — Para reentrenamiento

---

**Próxima revisión:** 16 Enero (después E2E)

