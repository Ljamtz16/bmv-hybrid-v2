# Checklist Operación Diaria

## 🚀 Ejecución del Pipeline (16:10 CDMX post-cierre)

```powershell
cd C:\Users\...\usa_hybrid_clean_v1
.\scripts\run_daily_pipeline.ps1
```

**Duración esperada:** ~2-3 minutos

## ✅ Validaciones Automáticas

El pipeline verifica automáticamente:
1. ✓ CSV freshness (T-1)
2. ✓ Features freshness (T-1)  
3. ✓ Signals purity (solo T-1)
4. ✓ Coherence <3% (entry vs CSV)
5. ✓ Traceability (metadata completa)

**Si falla:** Plan se guarda en `val\trade_plan_rollback.csv` y pipeline ABORTA

## 📊 Revisión Post-Ejecución

### 1. Health Check
```powershell
cat reports\health\daily_health_YYYY-MM-DD.json
```
**Revisar:** Status, Alerts (Errors/Warnings), Coverage

### 2. Trade Plan
```powershell
cat val\trade_plan.csv
```
**Campos clave:**
- `ticker`, `entry_price`, `tp_price`, `sl_price`
- `prob_win_cal` (objetivo >0.85)
- `etth_days` (esperado 2-5 días)
- `asof_date`, `data_freshness_date` (ambos deben ser ayer)
- `entry_source` (signal o csv_last_close si hubo override)

### 3. Snapshot Diario
```powershell
ls snapshots\YYYY-MM-DD\
```
**Archivos:**
- trade_plan.csv
- trade_plan_audit.parquet
- signals_with_gates.parquet
- health.json
- validation.log

## 📈 Ejecución del Plan

### Opción A: Paper Trading (recomendado para validación)
```powershell
# Registrar en Excel H3 (ya hecho automáticamente)
# Monitorear intradía sin operar real
.\scripts\run_intraday_monitor.ps1
```

### Opción B: Trading Real
1. Revisar plan manualmente
2. Ejecutar órdenes en broker
3. Monitorear con `monitor_intraday.py`

## 🔄 Monitor Intradía (Opcional)

Durante horas de mercado (09:30-16:00 NY):
```powershell
.\scripts\run_intraday_monitor.ps1
```
- Actualiza Excel H3 con precios actuales
- Marca TP_HIT / SL_HIT automáticamente
- Loop hasta las 21:00 UTC

## 📋 KPIs a Monitorear

### Diarios
- **Cobertura:** 15-25% (termóstato de gates activo)
- **Coherence:** max |entry - last_close| < 3%
- **Coverage health:** No debe caer <10% (ajuste -0.01 umbral)

### Semanales
- **Hit Rate:** >75% (objetivo 80-85%)
- **E[PnL] vs Real:** Gap <20%
- **Win Rate:** >80% en bitácora

### Mensuales (desde KPI reports)
```powershell
cat reports\forecast\kpi_monthly_summary.csv
```
- Sharpe Ratio
- Max Drawdown
- Total Return

## 🚨 Troubleshooting

### Pipeline falla en validación
```powershell
# Ver log detallado
cat tmp\validation_YYYY-MM-DD.log

# Revisar plan rollback
cat val\trade_plan_rollback.csv

# Re-ejecutar desde paso específico
python scripts\11_infer_and_gate.py
python scripts\40_make_trade_plan_with_tth.py
python scripts\test_forward_looking.py
```

### Excel bitácora no actualiza
- **Causa:** Excel abierto en Google Drive
- **Fix:** Cerrar Excel y re-ejecutar
```powershell
python scripts\bitacora_excel.py --add-plan val\trade_plan.csv
```

### Lockfile antiguo
```powershell
rm tmp\pipeline.lock
```

## 📅 Calendario Semanal

**Lunes-Viernes:**
- 16:10 CDMX: Ejecutar pipeline
- 16:15 CDMX: Revisar health + plan
- 16:30 CDMX: Ejecutar plan (si aplica)

**Sábado (opcional):**
```powershell
python scripts\36_weekly_summary.py
```

## 🎯 Siguiente Nivel

1. **Task Scheduler** (Windows):
   - Programa `run_daily_pipeline.ps1` a las 16:10 CDMX
   - Log rotado en `logs\pipeline_YYYY-MM-DD.txt`

2. **Intradía First-Touch**:
   - Entrenar TTH con datos 5m/15m
   - Etiquetar first_touch TP/SL
   - Ranking: `E[PnL] / ETTH_p50`

3. **Panel HTML**:
   - `reports\index.html` generado diario
   - Muestra: cobertura, Brier, drift, top signals

## 📞 Referencias Rápidas

**Archivos clave:**
- Plan: `val\trade_plan.csv`
- Signals: `data\daily\signals_with_gates.parquet`
- Health: `reports\health\daily_health_YYYY-MM-DD.json`
- Bitácora: `G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx`

**Scripts útiles:**
- `scripts\test_forward_looking.py` - Validación manual
- `scripts\monitor_intraday.py --once` - Snapshot de precios
- `scripts\bitacora_excel.py --summary` - Resumen bitácora
