# 🎯 DECISIÓN OPERATIVA: ¿QUÉ HAGO AHORA? (15 Enero, 10:30 CDMX)

---

## LA SITUACIÓN

### Lo que pasó ayer

Corrí una prueba de **predicción/inferencia** que dijo:

```
✅ RESULT: READY_FOR_FRESH_E2E
```

### Lo que descubrí HOY

Esa prueba tiene 2 **warnings reales**:

```
⚠️ WARNING A: No hay datos T-1 (2026-01-14) en features
   → Validé técnica, no operación

⚠️ WARNING B: Output incompleto (faltan etth_days, operable, gate_reasons)
   → Validé script intermedio, no pipeline FINAL
```

**Conclusión:** Status correcto es 🟡 **PARTIAL**, no 🟢 **PASS**.

---

## OPCIONES QUE TIENES AHORA

### OPCIÓN 1: Validar HOY (seguro, 30-60 min)

```
AHORA (15 Ene, 10:30-11:30 CDMX):
  ✅ Paso 1: Descargar datos T-1 frescos (2026-01-14)
  ✅ Paso 2: Generar features con esos datos
  ✅ Paso 3: Ejecutar full pipeline (inferencia + TTH + operability)
  ✅ Paso 4: Validar output final (todas columnas)
  ✅ Paso 5: Verificar fechas y freshness

11:30-14:30 CDMX:
  📖 Revisar documentación
  ☕ Descanso

14:30 CDMX:
  🟢 Ejecutar E2E_TEST_PROCEDURE.md con CONFIANZA
     (será confirmación, no primer test)

15:00-15:30 CDMX:
  ✅ Plan fresco generado
  ✅ Listo para operar mañana 08:30

VENTAJA: Ganas horas de confianza hoy  
RIESGO: Si algo falla, tiempo para debug sin presión
```

### OPCIÓN 2: Confiar en E2E Mañana (rápido, pero riesgoso)

```
14:30 CDMX MAÑANA:
  ✅ Ejecutar E2E_TEST_PROCEDURE.md (FULL)
     Incluye: descargas + features + inferencia + validación

15:00-15:30 CDMX:
  ⏳ Esperar resultados

15:30-16:00 CDMX:
  🎲 Decisión: PASS → operar, FAIL → ??? (sin tiempo)

VENTAJA: Menos trabajo hoy  
RIESGO: Si E2E falla a las 15:30, no puedes operar mañana 08:30
```

---

## MI RECOMENDACIÓN PROFESIONAL

### Ejecuta OPCIÓN 1 (Validación HOY)

**Razón:**

```
1. Tienes 4 horas de buffer (10:30-14:30)
   → Si falla, tienes tiempo de arreglarlo

2. E2E mañana a las 14:30 será confirmación, no primer test
   → Baja estrés operativo

3. Alineado con tu filosofía de "defensible + rigurosa"
   → Documentas hallazgos hoy, no mañana under pressure

4. NYSE está abierto 08:30-15:00 CDMX
   → Datos T-1 frescos disponibles AHORA
   → Si esperas, cambios intraday pueden afectar freshness
```

---

## EJECUTAR OPCIÓN 1: PASOS ESPECÍFICOS

### PASO 1: Descargar datos T-1 frescos (10:40-10:50 CDMX)

```powershell
cd "C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1"

# Identificar script de descarga
Get-ChildItem .\scripts\00*.ps1

# Ejecutar (típicamente es algo como):
.\scripts\00_download_daily_ohlcv.ps1

# O si es Python:
python .\scripts\00_download_daily_ohlcv.py

# Validar:
Get-ChildItem .\data\daily\ohlcv*.parquet | Select-Object LastWriteTime
# Esperado: Timestamp = 2026-01-15 (hoy)
```

**Criterio PASS:**
```
✅ Comando ejecuta sin error
✅ Archivo actualizado (LastWriteTime = hoy)
✅ Tamaño > anterior (nuevos datos agregados)
```

---

### PASO 2: Generar features con T-1 (10:50-11:05 CDMX)

```powershell
# Identificar script de features
Get-ChildItem .\scripts\09*.ps1

# Ejecutar (típicamente):
.\scripts\09_generate_features_daily.ps1

# O si es Python:
python .\scripts\09_generate_features_daily.py

# Validar:
$feat = Get-ChildItem .\data\daily\features_daily*.parquet | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "Features updated: $($feat.LastWriteTime)"

python -c "
import pandas as pd
df = pd.read_parquet('data/daily/features_daily_enhanced.parquet')
print(f'Rows: {len(df)}')
print(f'Date max: {df[\"timestamp\"].max() if \"timestamp\" in df.columns else \"N/A\"}')
"
```

**Criterio PASS:**
```
✅ Script ejecuta sin error
✅ features_daily_enhanced.parquet actualizado
✅ Rows > 26,694 (anterior)
✅ Última fecha incluye 2026-01-14
```

---

### PASO 3: Ejecutar full pipeline (inferencia + operability) (11:05-11:20 CDMX)

```powershell
# Backup artefactos viejos
Copy-Item .\data\daily\signals_with_gates.parquet `
          .\backups\signals_with_gates_nov25_backup.parquet -Force

# Ejecutar FULL pipeline (busca estos scripts):
python .\scripts\11_infer_and_gate.py           # Inferencia
python .\scripts\15_calculate_tth.py            # TTH (si existe)
python .\scripts\20_apply_operability.py        # Operability (si existe)
python .\scripts\33_generate_trade_plan.py      # Plan final

# O si existe un runner consolidado:
.\run_h3_daily.ps1

# Validar:
Get-ChildItem .\val\trade_plan.csv | Select-Object LastWriteTime
Get-ChildItem .\data\daily\signals*.parquet | Select-Object LastWriteTime
```

**Criterio PASS:**
```
✅ Todos los scripts ejecutan (exit 0)
✅ Archivos generados (trade_plan.csv o signals_with_gates.parquet)
✅ Timestamps = hoy (2026-01-15)
```

---

### PASO 4: Validar output FINAL (todas columnas) (11:20-11:35 CDMX)

```powershell
python -c "
import pandas as pd

# Leer output final
try:
    plan = pd.read_csv('val/trade_plan.csv')
except:
    plan = pd.read_parquet('data/daily/signals_with_gates.parquet')

print('='*60)
print('OUTPUT VALIDATION')
print('='*60)
print(f'Rows: {len(plan)}')
print(f'Columns: {len(plan.columns)}')

# Validar TODAS columnas críticas
required = ['ticker', 'entry_price', 'tp_price', 'sl_price', 'prob_win_cal']
optional = ['etth_days', 'operable', 'gate_reasons', 'asof_date']

print(f'\n✅ Required columns:')
for col in required:
    if col in plan.columns:
        print(f'  ✅ {col}')
    else:
        print(f'  ❌ {col} MISSING!')

print(f'\n⚠️ Optional columns:')
for col in optional:
    if col in plan.columns:
        print(f'  ✅ {col}')
    else:
        print(f'  ⚠️ {col} (not in this version)')

# Sample
print(f'\nSample (first 3 trades):')
display_cols = [c for c in required if c in plan.columns]
print(plan[display_cols].head(3).to_string())

print(f'\n✅ PASS: Output válido para operación')
"
```

**Criterio PASS:**
```
✅ Rows > 0 (hay trades)
✅ Todas columnas required presentes
✅ No hay NaN en entry/tp/sl/ticker
✅ prob_win_cal en rango [0.6, 1.0]
```

---

### PASO 5: Validar freshness con datos reales (11:35-11:45 CDMX)

```powershell
python -c "
import pandas as pd
from datetime import datetime, timedelta

plan = pd.read_csv('val/trade_plan.csv') if False else pd.read_parquet('data/daily/signals_with_gates.parquet')

print('='*60)
print('FRESHNESS VALIDATION')
print('='*60)

# Buscar columna de fecha
date_col = None
for col in ['asof_date', 'date', 'timestamp', 'entry_date']:
    if col in plan.columns:
        date_col = col
        break

if date_col:
    dates = pd.to_datetime(plan[date_col]).dt.date.unique()
    expected_date = (datetime.now() - timedelta(days=1)).date()
    
    print(f'Expected T-1: {expected_date}')
    print(f'Actual dates: {dates}')
    
    if expected_date in dates:
        print(f'✅ PASS: Plan generado para T-1 ({expected_date})')
    else:
        print(f'⚠️ WARNING: No T-1 exacto, pero dates: {dates}')
else:
    print('⚠️ No date column found, skipping freshness check')
"
```

**Criterio PASS:**
```
✅ asof_date incluye 2026-01-14 (T-1)
✅ Plan generado HOY (2026-01-15)
✅ Datos frescos, no cached
```

---

## TIMELINE SI EJECUTAS HOY

```
10:30 - Termino de escribir este documento
10:40 - PASO 1: Descargas (10 min)
10:50 - PASO 2: Features (15 min)
11:05 - PASO 3: Full pipeline (15 min)
11:20 - PASO 4: Validación (15 min)
11:35 - PASO 5: Freshness (10 min)

11:45 - Resultados
  └─ Si TODO PASS: 🟢 VALIDATED
  └─ Si algo falla: 🟡 DEBUG

12:30 - Fin debugging (si fue necesario)

14:30 - E2E_TEST_PROCEDURE.md (confirmación, no test)
15:30 - Trade plan final

16:00+ - Libre, plan seguro para mañana 08:30
```

---

## DECISIÓN FINAL

### ¿Ejecutas OPCIÓN 1 (HOY) u OPCIÓN 2 (MAÑANA)?

**YO RECOMIENDO:**

```
Ejecuta OPCIÓN 1 (HOY, ahora)

Razón: Tienes 4 horas de buffer seguro.
Beneficio: Mañana es confirmación, no first test.
Riesgo mitigado: Si falla, tiempo de debug.

Si todo PASS hoy:
  → Mañana 14:30 es puro formalismo
  → Confianza operativa: 100%

Si algo falla hoy:
  → Tienes 4 horas para investigar
  → Mañana 08:30 aún puedes operar (con cuidado)
  → Sábado puedes iterar sin presión
```

---

## ARCHIVO DE REFERENCIA

Documento con **análisis detallado de warnings**:
```
ANALISIS_WARNINGS_CRITICOS.md
```

---

**Decisión:** ¿HOY u MAÑANA?  
**Próximo:** Avísame qué haces, ejecuto los scripts contigo.

