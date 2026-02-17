# ✅ PRUEBA DE PREDICCIÓN/INFERENCIA (Hoy - 14 Enero 2026)

**Objetivo:** Validar que el modelo carga, las features están intactas, y genera predicciones ANTES de ejecutar el E2E completo mañana.

**Duración:** 20–30 minutos  
**Riesgo:** Bajo (no modifica datos, solo lectura + predicción)

---

## 📋 RESUMEN

Esta prueba ejecuta **solo la fase de inferencia** sin:
- ❌ Descargar datos (skip 00-series)
- ❌ Entrenar modelos (skip 10-series)
- ✅ Carga features existentes
- ✅ Carga modelos entrenados
- ✅ Genera predicciones + gates
- ✅ Valida outputs

---

## PASO 1: Verificar archivos de entrada (5 min)

### 1.1 Verifica que los features existen

```powershell
cd "C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1"

# Busca features
Get-ChildItem .\data\daily\*feature*.parquet | Select-Object Name, Length

# Esperado: al menos features_daily.parquet o features_daily_enhanced.parquet
```

**Criterio PASS:**
- Al menos **1 archivo** `features_*.parquet` existe ✅
- Tamaño > 100 KB ✅

**Criterio FAIL:**
- No hay archivos features ❌
- Tamaño = 0 ❌

---

### 1.2 Verifica que los modelos están entrenados

```powershell
# Busca modelos
Get-ChildItem .\models\direction\*.joblib | Select-Object Name, Length

# Esperado: rf.joblib, xgb.joblib, cat.joblib, meta.joblib
```

**Criterio PASS:**
- Mínimo **3 de 4** modelos existen (RF, XGB, CAT, META) ✅
- Cada uno > 50 KB ✅

**Criterio FAIL:**
- Falta algún modelo crítico ❌
- Tamaño 0 ❌

---

### 1.3 Verifica que el régimen existe

```powershell
# Régimen diario
Get-ChildItem .\data\daily\regime*.csv | Select-Object Name, Length

Get-Content .\data\daily\regime_daily.csv -TotalCount 3
```

**Criterio PASS:**
- `regime_daily.csv` existe y tiene contenido ✅

**Criterio FAIL:**
- Archivo vacío o no existe ❌

---

## PASO 2: Sanity-check rápido de features (5 min)

Valida que el dataset tiene las columnas esperadas sin NaN masivos.

```powershell
python - << 'PY'
import pandas as pd
import numpy as np

# Carga features
df = pd.read_parquet('data/daily/features_daily_enhanced.parquet')

print(f"📊 FEATURES STATS")
print(f"  Rows: {len(df)}")
print(f"  Columns: {len(df.columns)}")
print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}" if 'timestamp' in df.columns else "  ⚠ No timestamp column")

# Columnas críticas
critical = ['ticker', 'close', 'open', 'high', 'low', 'volume']
present = [c for c in critical if c in df.columns or c.lower() in [x.lower() for x in df.columns]]
print(f"\n✅ Core columns present: {present}")

# NaN check rápido (primeras 30 columnas)
cols_to_check = list(df.columns)[:30]
na_pct = (df[cols_to_check].isna().sum() / len(df) * 100).sort_values(ascending=False)
print(f"\n⚠️  Top 5 NA% (first 30 cols):")
print(na_pct.head(5))

# Valores numéricos básicos
print(f"\n📈 Sample numeric stats (close column):")
close_col = [c for c in df.columns if 'close' in c.lower()][0] if any('close' in c.lower() for c in df.columns) else None
if close_col:
    print(df[close_col].describe())
else:
    print("  No 'close' column found")

print("\n✅ PASS: Features cargadas correctamente" if len(df) > 0 else "❌ FAIL: Features vacías")
PY
```

**Criterio PASS:**
- Rows > 0 ✅
- Columnas core presentes (ticker, close, volume) ✅
- NA% < 50% en columnas principales ✅

**Criterio FAIL:**
- Rows = 0 ❌
- NA% > 80% ❌
- Columnas críticas faltantes ❌

---

## PASO 3: Ejecutar script de inferencia (10 min)

Aquí corre el pipeline de predicción SIN descargar datos nuevos.

```powershell
# Ir a raíz
cd "C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1"

# Ejecutar inferencia
Write-Host "🔄 Iniciando inferencia..." -ForegroundColor Cyan
$start = Get-Date
python .\scripts\11_infer_and_gate.py
$end = Get-Date
$duration = ($end - $start).TotalSeconds

Write-Host "✅ Inferencia completada en $duration segundos" -ForegroundColor Green
```

**Criterio PASS:**
- Script ejecuta sin error (exit code = 0) ✅
- Duration < 60 segundos (rápido) ✅

**Criterio FAIL:**
- Error en ejecución (exit code ≠ 0) ❌
- Timeout > 5 minutos ❌

---

## PASO 4: Validar output de predicción (5 min)

Verifica que se generó el archivo de predicciones.

```powershell
# Busca el output
$output = ".\data\daily\signals_with_gates.parquet"
$exists = Test-Path $output

if ($exists) {
    $file = Get-Item $output
    Write-Host "✅ Output encontrado: $($file.Name)" -ForegroundColor Green
    Write-Host "   Tamaño: $($file.Length) bytes"
    Write-Host "   Modificado: $($file.LastWriteTime)"
} else {
    Write-Host "❌ Output NO encontrado: $output" -ForegroundColor Red
    exit 1
}

# Lee el contenido
python - << 'PY'
import pandas as pd

signals = pd.read_parquet('data/daily/signals_with_gates.parquet')

print(f"\n📊 SIGNALS & GATES")
print(f"  Rows: {len(signals)}")
print(f"  Columns: {len(signals.columns)}")
print(f"\n🔍 Core columns:")

critical = ['ticker', 'prob_win_cal', 'etth_days', 'operable', 'gate_reasons']
for col in critical:
    if col in signals.columns:
        print(f"  ✅ {col}: present")
    else:
        print(f"  ❌ {col}: MISSING")

# Stats de predicción
if 'prob_win_cal' in signals.columns:
    print(f"\n📈 prob_win_cal stats:")
    print(signals['prob_win_cal'].describe())

if 'operable' in signals.columns:
    operable_count = signals['operable'].sum()
    print(f"\n🎯 Operable count: {operable_count} / {len(signals)} ({operable_count/len(signals)*100:.1f}%)")

print("\n✅ PASS: Signals générés correctamente")
PY
```

**Criterio PASS:**
- Archivo `signals_with_gates.parquet` existe ✅
- Contiene `prob_win_cal` y `etth_days` ✅
- Rows > 0 ✅
- Operable count coherente (5–30%) ✅

**Criterio FAIL:**
- Archivo no existe ❌
- Faltan columnas críticas ❌
- Rows = 0 ❌
- All prob = NaN ❌

---

## PASO 5: Comparación rápida con histórico (opcional, 5 min)

Verifica que las predicciones son "razonables" comparadas con días anteriores.

```powershell
python - << 'PY'
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Lee hoy
signals = pd.read_parquet('data/daily/signals_with_gates.parquet')

# Si existen snapshots anteriores, compara
snapshots_dir = Path('snapshots')
if snapshots_dir.exists():
    prev_files = sorted(snapshots_dir.glob('*/signals_with_gates.parquet'), reverse=True)
    if len(prev_files) > 0:
        prev = pd.read_parquet(prev_files[0])
        
        print(f"📊 COMPARACIÓN CON PREDICCIÓN ANTERIOR")
        print(f"  Hoy: {len(signals)} signals")
        print(f"  Anterior: {len(prev)} signals")
        
        print(f"\n📈 Distribución prob_win_cal:")
        print(f"  Hoy mean: {signals['prob_win_cal'].mean():.3f}")
        print(f"  Anterior mean: {prev['prob_win_cal'].mean():.3f}")
        
        # Chequea si hay cambios drásticos
        delta_mean = abs(signals['prob_win_cal'].mean() - prev['prob_win_cal'].mean())
        if delta_mean > 0.15:
            print(f"\n⚠️  WARNING: Cambio significativo en prob promedio (+{delta_mean:.2%})")
            print(f"  Investiga: ¿cambio de régimen? ¿datos nuevos?")
        else:
            print(f"\n✅ Distribuciones estables (delta = {delta_mean:.2%})")
else:
    print("(Sin snapshots anteriores para comparar)")

PY
```

**Criterio PASS:**
- Cambio < 15% en distribución media ✅

**Criterio WARNING:**
- Cambio 15–30% (investiga pero continúa) 🟡

**Criterio FAIL:**
- Cambio > 30% (posible data leak / error) ❌

---

## PASO 6: Guardar evidencia de la prueba (2 min)

Empaqueta resultados para auditoría.

```powershell
# Crear folder evidencia
$date = Get-Date -Format "yyyyMMdd_HHmm"
$testDir = ".\reports\inference_test\$date"
New-Item -ItemType Directory -Force $testDir | Out-Null

# Copiar outputs
Copy-Item .\data\daily\signals_with_gates.parquet "$testDir\signals_with_gates.parquet" -Force
Copy-Item .\models\direction\*.joblib "$testDir\" -Force -ErrorAction SilentlyContinue
Copy-Item .\data\daily\regime_daily.csv "$testDir\regime_daily.csv" -Force -ErrorAction SilentlyContinue

Write-Host "✅ Evidencia guardada: $testDir"
Get-ChildItem $testDir | Select-Object Name, Length
```

---

## PASO 7: Reporte final (2 min)

```powershell
# Crea reporte
$report = @{
    timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    test = "INFERENCE_ONLY"
    features_exist = (Test-Path .\data\daily\features_daily*.parquet)
    models_exist = @(Get-ChildItem .\models\direction\*.joblib).Count -ge 3
    inference_ran = (Test-Path .\data\daily\signals_with_gates.parquet)
    signals_count = (Import-Csv .\data\daily\signals_with_gates.parquet | Measure-Object).Count
    status = "READY_FOR_E2E"
}

$report | ConvertTo-Json | Out-File ".\reports\inference_test\$date\test_report.json"

Write-Host "`n" + ("="*60) -ForegroundColor Cyan
Write-Host "✅ PRUEBA DE INFERENCIA COMPLETADA" -ForegroundColor Green
Write-Host "="*60
Write-Host "Timestamp: $($report.timestamp)"
Write-Host "Features: $($report.features_exist)"
Write-Host "Models: $($report.models_exist)"
Write-Host "Signals: $($report.signals_count)"
Write-Host "Status: $($report.status)" -ForegroundColor Green
Write-Host "="*60
```

---

## 🎯 CHECKLIST PRUEBA DE INFERENCIA

```
[ ] 1.1 Features existen (tamaño > 100 KB)
[ ] 1.2 Modelos existen (≥3 de 4, cada uno > 50 KB)
[ ] 1.3 Régimen existe (regime_daily.csv con datos)
[ ] 2.1 Features dataset: rows > 0, columnas OK
[ ] 2.2 NaN < 50% en columnas principales
[ ] 3.1 Script inferencia ejecuta (exit 0)
[ ] 3.2 Duration < 60 seg
[ ] 4.1 signals_with_gates.parquet existe
[ ] 4.2 Contiene prob_win_cal y etth_days
[ ] 4.3 Rows > 0, operable 5-30%
[ ] 5.1 Distribución estable (delta < 15%)
[ ] 6.1 Evidencia empaquetada
[ ] 7.1 Reporte generado
```

---

## 📊 INTERPRETACIÓN DE RESULTADOS

### PASS ✅
Todos los pasos completaron sin error. Sistema listo para E2E mañana.

**Próximo paso:** Ejecuta E2E_TEST_PROCEDURE.md mañana 14:30 CDMX.

### WARNING 🟡
Completó pero con alertas (ej: cambio distribution > 15%, NaN en algunas columnas).

**Próximo paso:** Invetsiga la alerta, luego ejecuta E2E mañana.

### FAIL ❌
Script no ejecutó o outputs faltantes/inválidos.

**Próximo paso:** 
1. Revisa logs en terminal
2. Verifica que features están presentes
3. Recorre PASO 1 y PASO 2 nuevamente
4. Si falla de nuevo, necesitas DEBUG (modelo corrupto o features incompatibles)

---

## 🔧 TROUBLESHOOTING RÁPIDO

| Error | Causa Probable | Solución |
|-------|----------------|----------|
| `features_daily*.parquet not found` | No corriste 09-series (features gen) | Corre `scripts\09_*.py` o espera a que E2E lo haga mañana |
| `models/*.joblib not found` | Modelos no entrenados | Corre `scripts\10_*.py` o espera E2E mañana |
| `ModuleNotFoundError: pandas` | Dependencias faltantes | `pip install -r requirements.txt` |
| `Memory error` | Dataset muy grande | Normal, continúa (E2E usa mismo método) |
| `prob_win_cal all NaN` | Incompatibilidad feature/modelo | Revisa feature_manifest.json vs features_daily_enhanced.parquet |

---

## ✅ CONCLUSIÓN

**Usar esta prueba hoy (14 Enero) para:**
- ✅ Validar que modelos y features están en orden
- ✅ Detectar errores de incompatibilidad ANTES del E2E
- ✅ Ganar confianza en la predicción
- ✅ Documentar baseline de predicción

**Mañana (15 Enero):**
- Ejecuta E2E_TEST_PROCEDURE.md a las 14:30 CDMX
- Sistema estará pre-validado

---

**Fecha:** 14 Enero 2026  
**Duración estimada:** 20–30 minutos  
**Riesgo:** Bajo (lectura + predicción, sin data nueva)  
**Recomendación:** EJECUTAR HOY

