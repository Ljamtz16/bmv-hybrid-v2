# PREDICCIONES FORWARD-LOOKING: Actualización del Pipeline

## 📊 PROBLEMA IDENTIFICADO

**Antes:** El pipeline generaba predicciones usando precios **históricos desactualizados**:
- Las features se generaban con datos hasta el cierre de ayer (T-1 o anterior)
- Las predicciones usaban `close` histórico como `entry_price`
- El trade plan mostraba precios de entrada obsoletos (ej: NVDA $116 cuando el mercado está en $193)

**Resultado:** Las "predicciones" no eran realmente forward-looking, sino análisis retrospectivo.

---

## ✅ SOLUCIÓN IMPLEMENTADA

### Nuevo Flujo del Pipeline

El `run_daily_pipeline.ps1` ahora ejecuta **6 pasos** en lugar de 5:

```
0. REFRESH DATA (NUEVO) → Actualiza precios y regenera features
   ├─ download_us_prices.py    → Descarga último cierre disponible
   ├─ 00_download_daily.py     → Convierte a formato parquet wide
   ├─ 09_make_features_daily.py → Genera features técnicos
   ├─ 09c_add_context_features.py → Añade contexto (sector, earnings, etc.)
   └─ 08_make_targets_adaptive.py → Genera targets adaptativos por ATR/régimen

1. INFERENCE → 11_infer_and_gate.py (usa features actualizadas)
2. TRADE PLAN → 40_make_trade_plan_with_tth.py
3. BITÁCORA → bitacora_excel.py
4. HEALTH CHECKS → 41_daily_health_checks.py
5. TELEGRAM (opcional)
```

### Script Nuevo: `00_refresh_daily_data.py`

Orquesta la actualización completa de datos:
- Descarga precios **hasta el último cierre disponible** (T)
- Regenera features incluyendo el día más reciente
- Prepara `features_enhanced_binary_targets.parquet` actualizado

**Uso independiente:**
```powershell
.venv\Scripts\python.exe scripts\00_refresh_daily_data.py
```

---

## 🔄 CÓMO FUNCIONA AHORA

### Timeline de Predicción

```
T-1: Cierre anterior (datos históricos)
T:   Último cierre descargado → ENTRADA PARA PREDICCIÓN
T+1: Día siguiente → OBJETIVO DE PREDICCIÓN

Ejemplo (Nov 12, 2025):
- T-1: Nov 11 (NVDA cerró en $193.23)
- T:   Nov 12 10:00 AM → Descargamos cierre de Nov 11
- T+1: Nov 12 trading day → Predecimos movimiento basado en $193.23
```

### Ventanas de Ejecución

**Ejecución Pre-Market (antes de apertura T):**
```powershell
# Ejecutar entre 7:00-9:30 AM NY para tener predicciones antes de apertura
.\scripts\run_daily_pipeline.ps1
```
- Descarga cierre de T-1
- Predice movimiento para día T
- Entry price = último cierre disponible

**Ejecución Post-Market (después de cierre T):**
- Descarga cierre de T
- Predice movimiento para T+1
- Entry price = cierre de hoy

---

## 📂 ARCHIVOS MODIFICADOS

### 1. `scripts/00_refresh_daily_data.py` (NUEVO)
**Propósito:** Orquestador de actualización de datos diarios
**Dependencias:**
- `download_us_prices.py`
- `00_download_daily.py`
- `09_make_features_daily.py`
- `09c_add_context_features.py`
- `08_make_targets_adaptive.py`

### 2. `scripts/run_daily_pipeline.ps1` (MODIFICADO)
**Cambios:**
- Añade paso 0: `00_refresh_daily_data.py`
- Actualiza numeración de pasos (1/6 → 6/6)
- Header actualizado: "Data Refresh → Inference → ..."

---

## 🎯 IMPACTO EN LAS PREDICCIONES

### Antes vs Ahora

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Precio de entrada** | Histórico (días/semanas atrás) | Último cierre disponible (T-1) |
| **Predicción** | Retrospectiva | Forward-looking real |
| **Discrepancia intraday** | Enorme (NVDA $116 vs $193) | Mínima (solo movimiento de T-1 a T) |
| **Utilidad para trading** | Baja (datos viejos) | Alta (decisiones basadas en precios recientes) |

### Comportamiento del Monitor Intraday

El monitor (`monitor_intraday.py`) ahora tiene sentido completo:
- **Entry prices** en bitácora = último cierre descargado (T-1)
- **Precios descargados** (yfinance intraday) = mercado actual (T)
- **Discrepancia esperada** = movimiento real desde T-1 a T (normal)

**Ejemplo coherente:**
```
Trade Plan (generado 7:00 AM Nov 12):
  NVDA entry: $193.23 (cierre Nov 11)
  
Monitor (tracking 10:00 AM Nov 12):
  NVDA actual: $195.40 (movimiento +1.1% en pre-market)
  ✅ Esto es esperado y correcto
```

---

## ⚙️ CONFIGURACIÓN

### Variables de Entorno (opcional)

```powershell
# Archivo de tickers (default: data/us/tickers_master.csv)
$env:TICKERS_FILE = "data\us\tickers_custom.csv"

# Fecha de inicio para histórico (default: 2020-01-01)
$env:START_DATE = "2023-01-01"
```

### Ejecución Manual por Paso

Si necesitas ejecutar pasos individuales:

```powershell
# Solo actualizar datos
.venv\Scripts\python.exe scripts\00_refresh_daily_data.py

# Solo inference (requiere datos actualizados)
.venv\Scripts\python.exe scripts\11_infer_and_gate.py

# Solo trade plan (requiere signals)
.venv\Scripts\python.exe scripts\40_make_trade_plan_with_tth.py

# Pipeline completo (recomendado)
.\scripts\run_daily_pipeline.ps1
```

---

## 🚨 IMPORTANTE: Timing de Ejecución

### Pre-Market (Recomendado)
**Hora:** 7:00 - 9:00 AM NY (antes de apertura)
**Datos:** Cierre de ayer (T-1)
**Predicción:** Para día actual (T)
**Uso:** Preparar trade plan antes de apertura

### Post-Market
**Hora:** 16:30 - 20:00 (después de cierre)
**Datos:** Cierre de hoy (T)
**Predicción:** Para mañana (T+1)
**Uso:** Análisis nocturno, preparación anticipada

---

## 📈 VENTAJAS

1. **Predicciones reales:** Usa precios del último cierre disponible
2. **Coherencia:** Entry prices alineados con realidad de mercado
3. **Decisiones informadas:** Trade plan basado en datos recientes
4. **Monitor intraday útil:** Detecta TP/SL desde entry realista
5. **Automatización:** Un comando ejecuta todo el flujo

---

## 🔧 TROUBLESHOOTING

### Error: "No se generó signals_with_gates.parquet"
**Causa:** Falló inference por features desactualizadas
**Solución:**
```powershell
# Regenerar features manualmente
.venv\Scripts\python.exe scripts\00_refresh_daily_data.py
# Reintentar pipeline
.\scripts\run_daily_pipeline.ps1
```

### Warning: "Inference retornó código X"
**Causa:** Posible falta de datos en features
**Acción:** El pipeline continúa con signals existentes (si hay)

### Precios aún desactualizados
**Causa:** Yahoo Finance aún no publicó cierre reciente
**Solución:** Esperar 15-30 min después de cierre de mercado

---

## 📝 RESUMEN

**Cambio principal:** El pipeline ahora descarga precios actualizados y regenera features **antes** de hacer predicciones, asegurando que los modelos usen el último cierre disponible como punto de partida.

**Resultado:** Predicciones verdaderamente forward-looking en lugar de análisis retrospectivo con datos obsoletos.

**Uso:**
```powershell
# Ejecutar pipeline completo con datos actualizados
.\scripts\run_daily_pipeline.ps1

# Ver resultados
Import-Csv val\trade_plan.csv | Format-Table ticker,entry_price,prob_win,ETTH
```

---

**Fecha:** 2025-11-12  
**Versión:** Pipeline v2.0 (Forward-Looking)
