# USA Hybrid Clean V2 - Reporte de Validación
**Fecha:** 2025-11-10  
**Sistema:** USA Hybrid Clean V1 → V2 ML Enhanced

---

## ✅ Estructura de Carpetas Creada

### Data Layer
- ✅ `data/intraday5/buffer/` - Buffer temporal para datos 5m
- ✅ `data/intraday5/history/` - Histórico particionado 5m
- ✅ `data/intraday15/history/` - Histórico 15m (6 meses rolling)
- ✅ `data/daily/` - Datos diarios consolidados

### Models Layer
- ✅ `models/direction/` - Modelos de dirección (ensemble)
- ✅ `models/calibration/` - Calibradores por sector/régimen
- ✅ `models/tth/` - Modelos de time-to-hit

### Validation Layer
- ✅ `val/` - Scripts de validación walk-forward

---

## ✅ Archivos de Configuración

### `config/data_sources.yaml`
- Define proveedores y rutas para datos intradía y diarios
- Estructura: intraday5, intraday15, daily, tickers
- **Status:** Creado, requiere completar proveedores y tickers

### `config/policies.yaml`
- Umbrales dinámicos por régimen (low_vol, med_vol, high_vol)
- Límites de riesgo (capital_max, max_open, cooldown, per_ticker_cap)
- **Status:** Creado con valores iniciales

---

## ✅ Scripts Validados (Sintaxis OK)

### Capa 1: Data Core
| Script | Status | Propósito |
|--------|--------|-----------|
| `00_download_daily.py` | ✅ | Descarga diario → Parquet unificado |
| `00a_download_intraday_5m.py` | ✅ | Descarga 5m → buffer |
| `00b_rollup_5m_to_history.py` | ✅ | Rollup buffer → history particionado |
| `00c_backfill_intraday_15m_6m.py` | ✅ | Resample 5m→15m, retención 6m |

### Capa 2: Feature Engineering
| Script | Status | Propósito |
|--------|--------|-----------|
| `09_make_features_daily.py` | ✅ | Features diarios (momentum, vol, ATR, patterns) |
| `09b_make_features_intraday.py` | ✅ | Features intradía agregados (vol, EMA, breakouts) |

### Capa 3: Predictive Ensemble
| Script | Status | Propósito |
|--------|--------|-----------|
| `10_train_direction_ensemble.py` | ✅ | RF + XGBoost + CatBoost + meta-learner |
| `11_infer_and_gate.py` | ✅ | Inferencia con gates dinámicos por régimen |

### Capa 4: Calibración Probabilística
| Script | Status | Propósito |
|--------|--------|-----------|
| `10b_calibrate_probabilities.py` | ✅ | Calibración isotónica/Platt por sector |
| `46_relabel_and_update_calibration.py` | ✅ | Re-etiquetado + recalibración + update TTH |

### Capa 5: Temporal Layer (TTH)
| Script | Status | Propósito |
|--------|--------|-----------|
| `39_predict_time_to_hit.py` | ✅ | Predicción TTH con bandas p10–p90 |
| `40_make_trade_plan_with_tth.py` | ✅ | Planner con ranking E[PnL/time] |

### Capa 6: Evaluación First-Touch
| Script | Status | Propósito |
|--------|--------|-----------|
| `45_evaluate_first_touch_intraday.py` | ✅ | TP/SL first-touch en 5m (fallback 15m) |

### Capa 7: Meta-Learning / Regime
| Script | Status | Propósito |
|--------|--------|-----------|
| `12_detect_regime.py` | ✅ | Clasificación de régimen diario |

### Capa 8: Explainability
| Script | Status | Propósito |
|--------|--------|-----------|
| `13_explain_signals_shap.py` | ✅ | SHAP por señal con top features |

### Capa 9: Validación Pro
| Script | Status | Propósito |
|--------|--------|-----------|
| `val/walkforward_train_eval.py` | ✅ | Walk-forward + purged K-Fold |

---

## ✅ Dependencias Instaladas

Las siguientes librerías están instaladas y funcionando:
- ✅ `xgboost==3.1.1` - Ensemble (gradient boosting)
- ✅ `catboost==1.2.8` - Ensemble (gradient boosting)
- ✅ `shap==0.49.1` - Explainability (SHAP values)

**Dependencias adicionales instaladas:**
- `numba==0.62.1` - Aceleración numérica
- `llvmlite==0.45.1` - Backend para numba
- `graphviz==0.21` - Visualización de árboles
- `cloudpickle==3.1.2` - Serialización avanzada
- `slicer==0.0.8` - Slicing para SHAP

---

## 📋 Checklist de Implementación

### Fase 1: Datos (Semanas 1-2)
- [ ] Completar `config/data_sources.yaml` con proveedores reales
- [ ] Ejecutar `00_download_daily.py` para backfill histórico
- [ ] Ejecutar `00a_download_intraday_5m.py` para datos recientes
- [ ] Validar estructura particionada en `data/intraday5/history/`
- [ ] Configurar cron/scheduler para `00a` diario y `00b` nocturno

### Fase 2: Features (Semanas 2-3)
- [ ] Ejecutar `09_make_features_daily.py` y validar output
- [ ] Ejecutar `09b_make_features_intraday.py` y validar output
- [ ] Revisar correlaciones y eliminar features redundantes

### Fase 3: Modelado (Semanas 3-5)
- [x] Instalar dependencias: `pip install xgboost catboost` ✅ **Completado**
- [ ] Ejecutar `10_train_direction_ensemble.py` con datos históricos
- [ ] Validar AUC > 0.60 en ensemble
- [ ] Ejecutar `10b_calibrate_probabilities.py` por sector
- [ ] Validar Brier score < 0.15

### Fase 4: TTH y Planner (Semanas 5-6)
- [ ] Ejecutar `39_predict_time_to_hit.py` con labels first-touch
- [ ] Validar MAE TTH < 30 minutos
- [ ] Ejecutar `12_detect_regime.py` para clasificación diaria
- [ ] Integrar `40_make_trade_plan_with_tth.py` con régimen

### Fase 5: Evaluación y Feedback (Semanas 6-8)
- [ ] Ejecutar `45_evaluate_first_touch_intraday.py` en backtest
- [ ] Validar outcomes TP/SL sin sesgo
- [ ] Ejecutar `46_relabel_and_update_calibration.py` diario
- [ ] Monitorear Brier/ECE semanalmente

### Fase 6: Explainability y Validación (Semanas 8-10)
- [x] Instalar `shap`: `pip install shap` ✅ **Completado**
- [ ] Ejecutar `13_explain_signals_shap.py` por batch
- [ ] Ejecutar `val/walkforward_train_eval.py` trimestral
- [ ] Documentar métricas en reporte mensual

---

## 🎯 Métricas Objetivo (12-16 semanas)

| Métrica | Actual (V1) | Objetivo (V2) | Método |
|---------|-------------|---------------|---------|
| Precisión direccional | 55-60% | 62-68% | Ensemble + features |
| Win rate | 60-65% | 65-72% | Calibración + gates |
| Brier score | 0.16-0.18 | 0.10-0.13 | Calibración por régimen |
| ECE | 0.08-0.10 | ≤ 0.05 | Recalibración diaria |
| Error ETTH (abs.) | Alto | -20-30% | Labels first-touch |
| E[PnL/time] | Base | +10-20% | Ranking temporal |
| Drawdown | 15-20% | < 15% | Umbrales adaptativos |
| Cobertura | Volátil | 15-25% | Stacking + políticas |

---

## 🔧 Próximos Pasos Inmediatos

1. ~~**Instalar dependencias:**~~ ✅ **COMPLETADO**
   ```powershell
   pip install xgboost catboost shap
   ```
   - ✅ XGBoost 3.1.1
   - ✅ CatBoost 1.2.8
   - ✅ SHAP 0.49.1

2. **Completar configuración:**
   - Editar `config/data_sources.yaml` con tickers y proveedores
   - Ajustar umbrales en `config/policies.yaml` según backtests

3. **Ejecutar pipeline de datos:**
   ```powershell
   python scripts\00_download_daily.py
   python scripts\00a_download_intraday_5m.py
   python scripts\00b_rollup_5m_to_history.py
   ```

4. **Validar estructura de datos:**
   - Verificar `data/intraday5/history/ticker=*/date=*/`
   - Verificar schema (timestamp, open, high, low, close, volume, ticker)

5. **Entrenar primer modelo:**
   ```powershell
   python scripts\09_make_features_daily.py
   python scripts\10_train_direction_ensemble.py
   ```

---

## ✅ Conclusión

**Estado del sistema:** Todos los componentes base están creados y validados sintácticamente.

**Estructura:** ✅ Completa  
**Scripts:** ✅ 16/16 validados  
**Configuración:** ✅ Base creada  
**Dependencias:** ✅ Instaladas (xgboost, catboost, shap)

**Listo para:** Fase de implementación y pruebas con datos reales.

**Riesgos mitigados:**
- Estructura modular para facilitar debugging
- Scripts independientes para testing aislado
- Configuración centralizada para ajustes rápidos
- Validación sintáctica completa

---

**Generado:** 2025-11-10  
**Sistema:** USA Hybrid Clean V2 - ML Enhanced
