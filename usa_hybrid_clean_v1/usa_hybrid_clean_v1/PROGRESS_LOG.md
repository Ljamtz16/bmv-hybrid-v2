# USA Hybrid Clean V2 - Progress Log

**Fecha**: 2025-11-10  
**Estado**: Fase 1 completada, Fase 2-3 en progreso

---

## ✅ Fase 1: Infraestructura y Datos (COMPLETADO)

### 1.1 Configuración
- [x] Crear estructura de carpetas (data/, models/, val/, config/)
- [x] Crear config/data_sources.yaml con 18 tickers
- [x] Crear config/policies.yaml con thresholds por régimen
- [x] Instalar dependencias (xgboost 3.1.1, catboost 1.2.8, shap 0.49.1)

### 1.2 Descarga de Datos
- [x] 00_download_daily.py → **12,888 filas** (2023-2025, 18 tickers)
  - Archivo: `data/daily/ohlcv_daily.parquet`
- [x] 00a_download_intraday_5m.py → Sin datos (mercado cerrado domingo)
- [x] 00b_rollup_5m_to_history.py → Buffer vacío (esperado)

### 1.3 Preparación de Features
- [x] 09_make_features_daily.py → **12,888 filas con 8 features**
  - Features: ret_1d, ret_5d, ret_20d, vol_5d, vol_20d, tr, atr_14d, pos_in_range_20d
  - Archivo: `data/daily/features_daily.parquet`
  - Non-null counts: 12,528-12,870 (warmup de rolling windows)

### 1.4 Regímenes
- [x] 12_detect_regime.py → **12,546 filas clasificadas**
  - Distribución: low_vol (4,182), med_vol (4,182), high_vol (4,182)
  - NaN: 342 (warmup period)
  - Archivo: `data/daily/regime_daily.csv`

---

## ✅ Fase 2: Targets y Entrenamiento (COMPLETADO)

### 2.1 Generación de Targets
- [x] 08_make_targets.py → **4,681 samples etiquetados**
  - Target: Forward return 5d con threshold ±3%
  - Balance: **60.1% wins**, 39.9% losses
  - Archivo: `data/daily/features_with_targets.parquet`

### 2.2 Entrenamiento del Ensemble
- [x] 10_train_direction_ensemble.py → **AUC 0.6777**
  - Modelos: RandomForest, XGBoost, CatBoost, LogisticRegression (meta)
  - Dataset: 4,681 samples, 7 features
  - Target balance: 60.07% positive
  - Modelos guardados: `models/direction/{rf,xgb,cat,meta}.joblib`

### 2.3 Calibración
- [x] 10b_calibrate_probabilities.py → **Brier 0.0497** ✅ (objetivo <0.15)
  - Método: IsotonicRegression
  - Calibrador guardado: `models/calibration/calibrator.joblib`
  - Reliability diagram: `models/calibration/reliability_diagram.png`

---

## ✅ Fase 3: Inferencia y Gates (COMPLETADO)

### 3.1 Inferencia con Ensemble
- [x] 11_infer_and_gate.py → **9,664 señales válidas**
  - Proceso: Ensemble stacking + calibración + gates por régimen
  - Resultados por régimen:
    - **low_vol**: 3,112 señales (threshold 0.22)
    - **med_vol**: 3,550 señales (threshold 0.25)
    - **high_vol**: 3,002 señales (threshold 0.28)
  - Archivo: `data/daily/signals_with_gates.parquet`

---

## ⏳ Fase 4: Time-to-Hit y Evaluación (PENDIENTE)

### 4.1 TTH Prediction
- [ ] 39_predict_time_to_hit.py
  - Requiere: Etiquetas de first-touch TP/SL desde intraday
  - Objetivo: MAE < 0.5 días, p10-p90 bands

### 4.2 Trade Planning
- [ ] 40_make_trade_plan_with_tth.py
  - Ranking por E[PnL/time]
  - Top N signals según capital disponible

### 4.3 First-Touch Evaluation
- [ ] 45_evaluate_first_touch_intraday.py
  - Requiere: Datos intraday 5m (ejecutar en día de mercado)
  - Proceso: Detectar primer touch de TP/SL

### 4.4 Recalibración
- [ ] 46_relabel_and_update_calibration.py
  - Frecuencia: Diaria
  - Output: Calibradores actualizados, report_calibration.json

---

## ⏳ Fase 5: Explainability y Validation (PENDIENTE)

### 5.1 SHAP Explanations
- [ ] 13_explain_signals_shap.py
  - Top-5 features por señal
  - Output: `reports/shap_explanations.parquet`

### 5.2 Walk-Forward Validation
- [ ] val/walkforward_train_eval.py
  - TimeSeriesSplit con purged folds
  - Frecuencia: Trimestral
  - Output: `val/walkforward_results.csv`

---

## 📊 Métricas Actuales

| Métrica | Valor | Target V2 | Estado |
|---------|-------|-----------|--------|
| **AUC Ensemble** | 0.6777 | >0.60 | ✅ |
| **Brier Score** | 0.0497 | <0.15 | ✅ |
| **Target Balance** | 60.07% | 60-65% | ✅ |
| **Señales Filtradas** | 9,664 | N/A | ✅ |
| **Win Rate** | TBD | 65-72% | ⏳ |
| **Directional Accuracy** | TBD | 62-68% | ⏳ |

---

## 📝 Próximos Pasos

### Corto Plazo (Esta Semana)
1. **Esperar día de mercado** para ejecutar 00a_download_intraday_5m.py
2. Ejecutar 45_evaluate_first_touch_intraday.py con datos 5m
3. Etiquetar TTH real y entrenar 39_predict_time_to_hit.py
4. Generar trade plan con 40_make_trade_plan_with_tth.py

### Mediano Plazo (2-4 Semanas)
1. Implementar loop diario de recalibración (46_relabel_and_update_calibration.py)
2. Generar SHAP explanations (13_explain_signals_shap.py)
3. Backtest walk-forward completo (val/walkforward_train_eval.py)
4. Optimizar hyperparámetros de ensemble

### Largo Plazo (1-3 Meses)
1. Integrar features de patterns (20_detect_patterns.py)
2. Añadir contexto de earnings y eventos
3. Implementar sector rotation en features (09b_make_features_intraday.py)
4. Escalar a más tickers (50+)

---

## 🛠️ Configuración Técnica

**Tickers** (18):
- Tech: AAPL, MSFT, NVDA, AMD
- Auto: TSLA
- Retail: AMZN, WMT
- Financial: JPM, GS, MS
- Industrial: CAT
- Energy: XOM, CVX
- Health: PFE, JNJ
- ETFs: SPY, QQQ, IWM

**Modelos**:
- RandomForest: n_estimators=100
- XGBoost: n_estimators=100, eval_metric=logloss
- CatBoost: iterations=100
- Meta: LogisticRegression

**Calibración**:
- Método: IsotonicRegression (out_of_bounds=clip)
- Scope: Global (pendiente: por sector/régimen)

**Policy Thresholds**:
- low_vol: prob_threshold=0.22, etth_max=10d
- med_vol: prob_threshold=0.25, etth_max=8d
- high_vol: prob_threshold=0.28, etth_max=6d

---

## 📂 Archivos Clave Generados

```
data/
  daily/
    ohlcv_daily.parquet           ← 12,888 rows
    features_daily.parquet         ← 12,888 rows, 8 features
    features_with_targets.parquet  ← 4,681 labeled samples
    regime_daily.csv               ← 12,546 classified
    signals_with_gates.parquet     ← 9,664 filtered signals

models/
  direction/
    rf.joblib
    xgb.joblib
    cat.joblib
    meta.joblib
  calibration/
    calibrator.joblib
    reliability_diagram.png

config/
  data_sources.yaml
  policies.yaml
```

---

## ⚠️ Notas y Limitaciones

1. **Intraday data**: No disponible el domingo (mercado cerrado)
   - Requerir ejecución en día de mercado para fases 4-5
2. **Régimen NaN**: 342 filas sin clasificación (primeros 20d de warmup)
   - Esperado y correcto según diseño
3. **Target threshold**: Actualmente ±3% para TP/SL
   - Considerar optimización dinámica por ticker/volatilidad
4. **Calibración global**: Aún no segmentada por sector/régimen
   - Implementar en próxima iteración para mejor precisión

---

## 🎯 Objetivos V2 (Recordatorio)

- **Directional Accuracy**: 62-68% (vs 55-60% V1)
- **Win Rate**: 65-72% (vs 58-62% V1)
- **Risk Management**: E[TTH] < 7 días, adaptativo por régimen
- **Explainability**: SHAP values en cada señal
- **Feedback Loop**: Recalibración diaria automatizada
