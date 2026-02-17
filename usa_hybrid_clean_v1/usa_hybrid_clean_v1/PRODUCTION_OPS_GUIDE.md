# PRODUCTION OPERATIONS GUIDE
## Daily Trading Pipeline - Baseline-Calibrated-Q4-2025

### Status: ✅ PRODUCTION READY

---

## 1. DAILY WORKFLOW

### Morning Routine (Pre-Market)
```powershell
# Full pipeline: inference → trade plan → health checks
.\scripts\run_daily_pipeline.ps1

# Con notificación Telegram (opcional)
.\scripts\run_daily_pipeline.ps1 -SendTelegram
```

**Output files:**
- `data/daily/signals_with_gates.parquet` - Señales calibradas post-gates
- `val/trade_plan.csv` - Plan ejecutable con sizing
- `val/trade_plan_audit.parquet` - Auditoría completa de candidatos
- `reports/health/daily_health_YYYY-MM-DD.json` - Health check report

---

## 2. TRADE PLAN INTERPRETATION

### Columnas del plan ejecutable:
```
ticker          - Símbolo a tradear
regime          - Régimen de volatilidad (low_vol/med_vol/high_vol)
prob_win_cal    - P(win) calibrada por régimen
entry_price     - Precio de entrada
qty             - Cantidad a comprar (entero)
position_cash   - Capital asignado ($)
exp_pnl         - E[PnL] esperado (fracción del capital)
exp_pnl_net     - E[PnL] neto después de costos
etth_days       - Tiempo estimado hasta evento (proxy ATR)
epnl_time       - Eficiencia: E[PnL]/tiempo (métrica de ranking)
```

### Ejemplo de lectura:
```
NVDA,high_vol,0.973,116.10,1,125.0,0.117,0.116,0.83,0.14
```
- Comprar 1 acción de NVDA a ~$116.10
- Régimen: alta volatilidad → threshold 0.65
- P(win) calibrada: 97.3%
- Capital: $125
- E[PnL] neto: +11.6% en ~0.8 días
- Eficiencia: 0.14 (mejor ranking)

---

## 3. HEALTH CHECK ALERTS

### Niveles de severidad:

**🔴 ERROR (Stop Trading)**
- Señales < 10 absolutas
- Calibrators faltantes por régimen
- Features con >50% NaN

**⚠️ WARNING (Revisar antes de tradear)**
- Brier > 0.14 o ECE > 0.05
- Coverage < 15% o > 35%
- PSI > 0.2 en features clave
- Concentración top-5 > 50%
- Sesgo de régimen > 60%

**✅ INFO**
- Targets no disponibles (modo forward-looking)
- Drift dentro de límites normales

### Acciones correctivas:

| Alert | Acción |
|-------|--------|
| ECE > 0.07 por 2 días | Recalibrar: `python scripts/calibrate_per_regime_v2.py` |
| Coverage < 15% | Revisar thresholds en `config/policies.yaml` (bajar 0.02) |
| Coverage > 35% | Revisar thresholds en `config/policies.yaml` (subir 0.02) |
| PSI > 0.3 | Reentrenar modelos: `python scripts/10_train_direction_ensemble_WALKFORWARD.py` |
| Concentración > 50% | Aplicar limits por ticker en el planner |

---

## 4. GUARDRAILS ACTIVOS

### Capital y sizing (config/guardrails.yaml):
```yaml
account_cash: 1000.0      # Total disponible
per_trade_target: 250.0   # Por posición
max_positions: 8          # Máximo simultáneo
max_per_ticker: 2         # Límite por símbolo
fee_pct: 0.0005           # 5 bps costo
```

### Probability gates por régimen:
```yaml
low_vol: 0.60    # Baja volatilidad → menos restrictivo
med_vol: 0.62    # Medio
high_vol: 0.65   # Alta volatilidad → más restrictivo
```

### Risk limits:
- Top 5 tickers: ≤ 50% exposición
- Single ticker: ≤ 25% exposición
- Single sector: ≤ 40% exposición

---

## 5. MONITORING DASHBOARD (Manual)

### Métricas diarias a revisar:

**Calidad de modelo:**
```python
import json
with open('reports/health/daily_health_2025-11-11.json') as f:
    h = json.load(f)
    
print(f"Brier: {h['metrics']['quality']['brier']:.4f}")  # < 0.14
print(f"ECE: {h['metrics']['quality']['ece']:.4f}")      # < 0.05
```

**Cobertura:**
```python
cov = h['metrics']['coverage']
print(f"Signals: {cov['signals_count']}")
print(f"Coverage: {cov['coverage_pct']:.1f}%")  # 15-35%
```

**Regímenes:**
```python
reg = h['metrics']['regime']['regime_distribution']
for r, pct in reg.items():
    print(f"{r}: {pct:.1f}%")
```

---

## 6. SCHEDULED TASK (Windows)

### Crear tarea programada (ejecutar como Admin):
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"C:\path\to\scripts\run_daily_pipeline.ps1`""

$trigger = New-ScheduledTaskTrigger -Daily -At "4:30PM"

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName "TradingPipeline_Daily" `
    -Action $action -Trigger $trigger -Principal $principal `
    -Description "Daily inference + trade plan + health checks"
```

### Verificar ejecución:
```powershell
Get-ScheduledTask -TaskName "TradingPipeline_Daily" | Get-ScheduledTaskInfo
```

---

## 7. BASELINE VERSIONING

### Baseline actual: `Baseline-Calibrated-Q4-2025`

**Artefactos versionados:**
```
models/direction/Baseline-Calibrated-Q4-2025/
  ├── rf.joblib
  ├── xgb.joblib
  ├── cat.joblib
  └── meta.joblib

models/calibration/Baseline-Calibrated-Q4-2025/
  ├── calibrator_iso_low_vol.joblib
  ├── calibrator_iso_med_vol.joblib
  ├── calibrator_iso_high_vol.joblib
  ├── calibrator_platt_low_vol.joblib
  ├── calibrator_platt_med_vol.joblib
  └── calibrator_platt_high_vol.joblib

val/Baseline-Calibrated-Q4-2025/
  ├── val_predictions.parquet
  ├── oos_predictions_calibrated.parquet
  └── walkforward_results.csv

reports/validation/Baseline-Calibrated-Q4-2025/
  ├── validation_report.txt
  ├── calibration_curves_*.png
  └── lift_curves_*.png
```

**Métricas OOS (Walk-Forward):**
- ROC-AUC: 0.8939
- Brier: 0.1279
- ECE: 0.0282
- Lift@10%: 1.71x
- Regime Brier: 0.115–0.135

### Rollback a baseline anterior:
```bash
# Copiar artefactos del snapshot deseado
cp -r models/direction/Baseline-Previous/* models/direction/
cp -r models/calibration/Baseline-Previous/* models/calibration/
```

---

## 8. NEXT MILESTONES

### ✅ Completado (Q4-2025):
- [x] Walk-forward validation sin leakage
- [x] Adaptive ATR% targets
- [x] Per-regime calibration (temp + iso/platt)
- [x] E[PnL]/time ranking con proxy ETTH
- [x] Daily pipeline con health checks
- [x] Executable sizing con guardrails

### 🔄 En progreso:
- [ ] Intraday validation (15m bars)
- [ ] Time-to-hit (TTH) model (script 39)
- [ ] First-touch labeling (scripts 00a/00b/00c)

### 📋 Roadmap Q1-2026:
- [ ] TTH integration en ranking: `P(TP≺SL) * E[PnL] / ETTH_p50`
- [ ] Confidence bands (p10-p90) en trade plan
- [ ] Sector rotation optimizer
- [ ] Multi-timeframe features (daily + intraday)
- [ ] Adaptive thresholds con Bayesian optimization

---

## 9. TROUBLESHOOTING

### Problema: "KeyError: 'regime'"
**Causa:** regime_daily.csv vacío o malformado
**Fix:**
```bash
python scripts/12_detect_regime.py  # Regenerar regímenes
```
O el script usará fallback por ATR% automáticamente.

### Problema: "ValueError: could not convert string to float"
**Causa:** Columna no-numérica en features
**Fix:** Ya resuelto con filtro `pd.api.types.is_numeric_dtype()` en feature selection.

### Problema: ECE alto (> 0.07)
**Causa:** Probabilities drift o data shift
**Fix:**
```bash
python scripts/calibrate_per_regime_v2.py  # Recalibrar
python scripts/validate_model_quality.py   # Verificar
```

### Problema: Trade plan vacío
**Causa:** Gates muy restrictivos
**Fix:** Revisar `config/policies.yaml` → bajar thresholds 0.02

---

## 10. CONTACTS & ESCALATION

### Alertas críticas (> 2 días consecutivos):
1. Revisar `reports/health/` últimos 3 días
2. Comparar con baseline metrics
3. Decidir: recalibrar vs. reentrenar
4. Documentar cambios en `CHANGELOG.md`

### Performance degradation:
- Brier increase > 0.03: Recalibrar
- AUC drop > 0.05: Reentrenar
- Persistent drift (PSI > 0.3): Feature engineering

---

## QUICK REFERENCE

**Ejecutar pipeline completo:**
```powershell
.\scripts\run_daily_pipeline.ps1
```

**Solo inference:**
```bash
python scripts/11_infer_and_gate.py
```

**Solo trade plan:**
```bash
python scripts/40_make_trade_plan_with_tth.py
```

**Health checks:**
```bash
python scripts/41_daily_health_checks.py
```

**Ver último health report:**
```bash
cat reports/health/daily_health_$(date +%Y-%m-%d).json | jq .summary
```

---

**Última actualización:** 2025-11-11  
**Baseline:** Baseline-Calibrated-Q4-2025  
**Status:** ✅ Production Ready
