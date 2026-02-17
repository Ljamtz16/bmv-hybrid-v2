# ⚠️ ANÁLISIS CRÍTICO DE WARNINGS — PRUEBA DE PREDICCIÓN/INFERENCIA

**Fecha:** 15 Enero 2026  
**Propósito:** Identificar qué los 2 warnings significan REALMENTE y por qué invalidan ciertos criterios

---

## RESUMEN EJECUTIVO

La prueba de predicción/inferencia que ejecuté ayer tiene status **técnico PASS**, pero **operativo PARTIAL**. 

**No es un defecto del sistema, sino una limitación del test mismo.**

```
✅ LO QUE VALIDÉ CORRECTAMENTE:
  • Sistema técnicamente no rompe
  • Scripts ejecutan sin error
  • Modelos están presentes y cargables
  • Dependencias funcionan

⚠️ LO QUE NO VALIDÉ (y es crítico):
  • Datos T-1 frescos (2026-01-14)
  • Output MODERNO con todas las columnas
  • Gating/operability con datos actuales
  • Freshness/macro risk con datos reales
```

---

## WARNING A: NO HAY DATOS T-1 (2026-01-14) {#warning-a}

### Qué Significa

El dataset de features llega hasta 2023. Cuando el script 11_infer_and_gate.py intentó encontrar datos para T-1 (2026-01-14), no encontró nada:

```
[INFO] Filtrado a T-1=2026-01-14: 0/26694 filas
[WARN] No hay datos tras merge de régimen
```

### Por Qué Es Un Warning Real

Según tu propia documentación (VALIDACION_FINAL_CHECKLIST.md, 3.3 Freshness):

```
**CRITERIO FAIL CRÍTICO si:**
- Fechas inválidas o ausentes SIN EXPLICACIÓN
- Plan con fechas "viejas" SIN EXPLICACIÓN
```

En la prueba que corrí:
- ❌ **No** generé datos con 2026-01-14
- ❌ **No** validé que el sistema GATEA correctamente con datos actuales
- ❌ **No** confirmé que "macro risk", "regime detection", "freshness checks" funcionen

**Consecuencia:** 
La prueba validó "inferencia en el vacío" (con datos históricos), no "inferencia operacional" (con datos vivos).

### Cómo Afecta Criterios Documentados

| Criterio | Validé? | Status |
|----------|---------|--------|
| 3.3 Freshness (T-1 coherente) | ❌ NO | ⚠️ PARTIAL |
| 3.5 Guardrails (regime gating) | ❌ NO | ⚠️ PARTIAL |
| 3.2 Health (validación régimen) | ❌ NO | ⚠️ PARTIAL |
| **Operability decisiones** | ❌ NO | ⚠️ PARTIAL |

**Veredicto:** ⚠️ **Esta prueba no es suficiente para validar "operabilidad".**

---

## WARNING B: OUTPUT INCOMPLETO (COLUMNAS FALTANTES) {#warning-b}

### Qué Significa

El archivo `signals_with_gates.parquet` que leí tiene:

```
Columnas Presentes:
  ✅ ticker
  ✅ prob_win_cal

Columnas FALTANTES (según tu GUIA_OPERATIVA):
  ❌ etth_days (Time-To-Hit)
  ❌ operable (gate status)
  ❌ gate_reasons (por qué se aceptó/rechazó)
```

### Por Qué Es Un Warning Real (Señal de Versión Desalineada)

Este output es de **25 Noviembre 2025**. Tu sistema moderno (según documentación de 14 Enero 2026) genera:

```
Archivo esperado MODERNO:
  ticker ✅
  entry_price ✅
  tp_price ✅
  sl_price ✅
  prob_win_cal ✅
  etth_days ⚠️ (FALTA en archivo viejo)
  operable ⚠️ (FALTA en archivo viejo)
  gate_reasons ⚠️ (FALTA en archivo viejo)
```

### Diagnóstico

Hay 3 posibilidades (todas válidas):

**Opción 1: Columnas agregadas en fase posterior**

```
Pipeline phases:
  11_infer_and_gate.py
    ↓ (genera: prob_win_cal)
  15_calculate_tth.py (o similar)
    ↓ (agrega: etth_days)
  20_operability.py
    ↓ (agrega: operable, gate_reasons)
  val/trade_plan.csv (salida final)
```

**Opción 2: Archivos parciales en `data/daily/`**

```
data/daily/:
  signals_with_gates.parquet (intermedio, Nov 2025)
  ↓ (después de full run)
  forecast_with_tth.parquet (TTH agregado)
  ↓ (después de operability)
  trade_plan_ready.parquet (final, todas columnas)
```

**Opción 3: Script cambiado, pero output guardado es viejo**

```
Escenario:
  • 11_infer_and_gate.py cambió desde Nov → agrega más columnas
  • El parquet guardado en data/daily es un BACKUP viejo
  • Cuando full pipeline corre, sobrescribe con versión nueva
```

### Cómo Afecta Validación

```
❌ NO PUEDO VALIDAR:
  • Que etth_days se calcula correctamente
  • Que gate_reasons es coherente
  • Que operable decision es binaria (True/False)

⚠️ SOLO VALIDÉ:
  • Que ticker existe
  • Que prob_win_cal está presente
  • Que valores son razonables (76-97%)
```

**Veredicto:** ⚠️ **Esta prueba no valida el output FINAL que operarás.**

---

## IMPACTO REAL EN TU OPERACIÓN

### Qué Pasará Mañana si Ejecutas E2E Completo (14:30 CDMX)

```
ESCENARIO A (Esperado - Todo OK):
  1. E2E descarga OHLCV 2026-01-14 ✅
  2. Genera features con 2026-01-14 ✅
  3. Corre inferencia: prob_win_cal ✅
  4. Agrega TTH: etth_days ✅
  5. Agrega operability: operable, gate_reasons ✅
  6. Genera val/trade_plan.csv ✅
  
  RESULTADO: PASS ✅ → Operas mañana 08:30 CDMX

ESCENARIO B (Si hay versión mismatch):
  1-2. OK (datos frescos)
  3. Corre inferencia pero genera parquet parcial ⚠️
  4. Falta TTH (si script 15_* no existe o cambió)
  5. Falta operability (si no corre o outputs no se unen)
  6. Generates val/trade_plan.csv pero sin etth_days/operable
  
  RESULTADO: WARNING 🟡 → Documentas y requiere DEBUG

ESCENARIO C (Falsa alarma - Mejor caso):
  1-6. Todo OK, las columnas se agregan en full pipeline
  
  RESULTADO: PASS ✅ → La prueba parcial fue OK, full es mejor
```

---

## REFRAMING: QUÉ SIGNIFICA REALMENTE "READY_FOR_FRESH_E2E"

Tu pregunta original fue:

> "¿Está el sistema ready para operar mañana con E2E?"

Mi respuesta fue:

> "Status: READY_FOR_FRESH_E2E" ✅

**Eso fue IMPRECISO.** Debería haber sido:

```
✅ TÉCNICAMENTE READY:
  • Inferencia script no rompe
  • Modelos cargan sin error
  • Dependencias OK
  • Puede procesar 26K rows en 6 seg

⚠️ OPERATIVAMENTE PARCIAL:
  • No validé con datos T-1 frescos
  • No validé output FINAL (todas columnas)
  • No validé gating decisiones con datos reales
  • No validé freshness/macro risk checks

🟡 VEREDICTO PRECISO:
  "Sistema técnicamente funciona. 
   Falta validar con datos frescos + output moderno.
   Listo para E2E, pero habrá sorpresas posibles."
```

---

## SOLUCIÓN: 4º PASO DE VALIDACIÓN ANTES DE OPERAR

Para convertir **PARTIAL → COMPLETE**, necesitas ejecutar (en orden):

### PASO 1: Asegurar T-1 Real en Features

```powershell
# Ejecutar SOLO el bloque de descargas + features (sin inferencia)

# Scripts a correr:
.\scripts\00_download_daily_ohlcv.ps1  # Descarga 2026-01-14
.\scripts\09_generate_features_daily.ps1  # Features con 2026-01-14

# Validar:
Get-ChildItem .\data\daily\features_daily*.parquet | Select-Object LastWriteTime

# Esperado: Timestamp = 2026-01-15 (hoy)
```

**Criterio PASS:**
```
✅ features_daily.parquet tiene timestamp hoy
✅ Contiene rows con 2026-01-14 en columna timestamp/date
✅ NaN < 5% (puede aumentar levemente con datos nuevos)
```

---

### PASO 2: Backup Artefactos Viejos

```powershell
# Evitar que el script lea caches viejos

Copy-Item .\data\daily\signals_with_gates.parquet `
          .\backups\signals_with_gates_nov25_backup.parquet -Force

Remove-Item .\data\daily\signals_with_gates.parquet -Force

# Esto obliga al script a regenerar
```

**Criterio PASS:**
```
✅ Archivo viejo en backup
✅ data/daily/ limpio
```

---

### PASO 3: Ejecutar Inferencia + TTH + Operability (Full Stack)

```powershell
# Correr el FULL inference chain, no solo 11_infer

.\scripts\11_infer_and_gate.py           # Inferencia
.\scripts\15_calculate_tth.py            # TTH (si existe)
.\scripts\20_apply_operability.py        # Gates (si existe)
.\scripts\33_generate_trade_plan.py      # Plan final
```

**Criterio PASS:**
```
✅ Todos los scripts ejecutan (exit 0)
✅ No hay errores de dependencia
```

---

### PASO 4: Validar Output FINAL (Todas Columnas)

```powershell
python -c "
import pandas as pd

# Leer output FINAL (no intermedio)
plan = pd.read_csv('val/trade_plan.csv')

# Validar TODAS las columnas esperadas
required = ['ticker', 'entry_price', 'tp_price', 'sl_price', 
            'prob_win_cal', 'etth_days', 'operable', 'gate_reasons']

missing = [c for c in required if c not in plan.columns]

if missing:
    print(f'❌ FALTA: {missing}')
    exit(1)
else:
    print(f'✅ PASS: Todas {len(required)} columnas presentes')
    print(f'  Rows: {len(plan)}')
    print(f'  Sample:')
    print(plan.head(3)[required])
"
```

**Criterio PASS:**
```
✅ ticker presente
✅ entry_price, tp_price, sl_price presentes
✅ prob_win_cal presente (76-97%)
✅ etth_days presente (números positivos)
✅ operable presente (True/False o 1/0)
✅ gate_reasons presente (texto con razón)
```

---

### PASO 5: Validar Freshness con Datos Reales

```powershell
python -c "
import pandas as pd
from datetime import datetime, timedelta

plan = pd.read_csv('val/trade_plan.csv')

# Validar T-1
expected_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
actual_dates = plan['asof_date'].unique() if 'asof_date' in plan.columns else ['UNKNOWN']

if expected_date in str(actual_dates):
    print(f'✅ PASS: Plan generado para T-1 ({expected_date})')
else:
    print(f'⚠️ WARNING: Esperado {expected_date}, encontrado {actual_dates}')

print(f'Sample dates: {actual_dates}')
"
```

**Criterio PASS:**
```
✅ asof_date = 2026-01-14 (T-1)
✅ Plan fresco para operación mañana
```

---

## TIMELINE: CUÁNDO EJECUTAR ESTOS 5 PASOS

### Opción A: Hoy (15 Enero) antes de 14:30 CDMX

Si tienes tiempo libre ahora:
1. Ejecuta PASOS 1-5
2. Si TODOS son PASS → Operación mañana es segura
3. Si alguno falla → DEBUG antes de operar

**Ventaja:** Ganas confianza hoy  
**Riesgo:** Menos tiempo para debug si falla

### Opción B: Mañana 14:30 CDMX (incluido en E2E)

E2E_TEST_PROCEDURE.md ya hace esto implícitamente:
- PASO 2: Descarga datos
- PASO 3: Genera features
- PASO 2 (main): Ejecuta `run_h3_daily.ps1` (que corre 11 + 15 + 20 + 33)
- PASO 4: Valida output

**Ventaja:** Es parte del flujo normal  
**Riesgo:** Sorpresas durante operación

---

## MI RECOMENDACIÓN

**Ejecuta los PASOS 1-5 HOY (ahora o dentro de 1 hora).**

**Razón:**

```
Hoy tienes el lujo de:
  ✅ Tiempo para debug sin presión
  ✅ No hay mercado abierto
  ✅ Puedes parar y investigar

Mañana 14:30 CDMX:
  ⚠️ NYSE abierto (datos actualizándose)
  ⚠️ Pressione operacional
  ⚠️ Si falla, tienes 30 min para fijar
```

Si hoy todo PASS, mañana solo ejecutas con confianza.

---

## RESUMEN: WARNINGS → ACCIONES

| Warning | Significa | Acción |
|---------|-----------|--------|
| **A: No T-1** | Prueba con datos viejos | Ejecutar PASOS 1-2 (descarga + features) |
| **B: Output incompleto** | Versión desalineada | Ejecutar PASOS 3-5 (full stack + validación) |

**Resultado esperado:**
```
Antes: ⚠️ READY_FOR_FRESH_E2E (impreciso)
Después: 🟢 VALIDATED_FOR_OPERATION (preciso)
```

---

## DOCUMENTACIÓN RESULTADO

Archivo: **CONSOLIDADO_RESULTADOS_TODAS_PRUEBAS.md**  
Actualización: Agregar sección "WARNINGS CRÍTICOS Y CÓMO RESOLVERLOS"

**Status actual:** ⚠️ **Técnico PASS, Operativo PARTIAL**  
**Status objetivo:** 🟢 **Técnico + Operativo PASS**  
**Camino:** PASOS 1-5 de validación fresca

---

**Documento creado:** 15 Enero 2026, 10:30 CDMX  
**Próximo paso:** Decide si ejecutas validación fresca HOY o MAÑANA 14:30

