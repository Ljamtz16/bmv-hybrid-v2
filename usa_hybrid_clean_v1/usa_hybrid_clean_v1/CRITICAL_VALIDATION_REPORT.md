# CRITICAL VALIDATION REPORT - USA Hybrid Clean V2

**Fecha**: 2025-11-10  
**Estado**: ⚠️ MODELO NO APTO PARA PRODUCCIÓN (requiere trabajo adicional)

---

## 🚨 HALLAZGOS CRÍTICOS

### 1. Data Leakage Detectado y Corregido

**Problema Original:**
- AUC reportado: **0.9769** (imposible)
- Brier reportado: **0.0497** (demasiado bueno)
- Top-decile hit rate: **99.5%**

**Causa:**
- Modelos entrenados y calibrados en **TODO el dataset**
- Sin separación train/test temporal
- Calibrador veía los mismos datos que el ensemble

**Corrección Aplicada:**
✅ Implementado walk-forward validation con TimeSeriesSplit (5 folds)
✅ Separación temporal estricta (train → test sin solapamiento)
✅ Métricas OOS reales

---

## 📊 MÉTRICAS REALES (Out-of-Sample)

### Baseline (7 features básicas)
```
AUC OOS:   0.5371 ± 0.0195
Brier OOS: 0.3761 ± 0.0224
```

### Con features de contexto (26 features)
```
AUC OOS:   0.5549 ± 0.0230
Brier OOS: 0.3622 ± 0.0393
```

**Mejora**: +1.8 pp en AUC, pero aún **muy lejos del objetivo (0.60+)**

---

## 🔍 DIAGNÓSTICO: ¿Por qué el modelo no funciona?

### Hipótesis 1: Features insuficientes (PARCIAL) ✅ Intentado
- Agregamos 18 features de contexto (gap, HH/LL, day-of-week, momentum)
- Resultado: Mejora **marginal** (0.537 → 0.555)
- **Conclusión**: Features ayudan, pero no son suficientes

### Hipótesis 2: Target mal definido (CRÍTICO) ⚠️
**Problema actual:**
- Target = 1 si `ret_5d > 3%` (TP)
- Target = 0 si `ret_5d < -3%` (SL)
- **Ignora todo lo intermedio** (datos descartados)

**Issues:**
1. **Pérdida de información**: Descartamos ~60% de los datos
2. **Binario rígido**: No captura magnitud del movimiento
3. **Fixed threshold**: 3% no es óptimo para todos los tickers/regímenes

**Solución propuesta:**
- Cambiar a **regresión**: Predecir `ret_5d` directamente
- O target adaptativo por volatilidad del ticker

### Hipótesis 3: Horizonte temporal inadecuado (PROBABLE) ⚠️
- 5 días es **swing trading**, no **day trading**
- En 5 días hay mucho **ruido no predecible** (noticias, earnings, macro)
- Mejor: **Horizonte 1-2 días** o **intraday** con context claro

### Hipótesis 4: Dataset pequeño (CONFIRMADO) ⚠️
```
Samples efectivos: 4,229 (post-cleanup)
Tickers: 18
Periodo: Mar 2023 - Oct 2025 (~2.5 años)
```

**Issues:**
- ~235 samples/ticker → insuficiente para ML robusto
- Poco histórico → no captura ciclos completos
- Pocos tickers → poca diversidad

**Solución:**
- Expandir a **50-100 tickers**
- Ampliar histórico a **5+ años** (desde 2019)
- O cambiar a **intraday** (más samples por día)

### Hipótesis 5: Features no tienen poder predictivo real (POSIBLE) ⚠️
**Realidad del mercado:**
- Returns de corto plazo son **casi aleatorios** (random walk)
- Momentum/volatility/technical son **señales débiles**
- Competencia eficiente → alpha decay rápido

**Qué falta:**
- **Fundamentals**: P/E, earnings surprise, guidance
- **Sentiment**: News sentiment, social media, analyst ratings
- **Microstructure**: Order flow, bid-ask, volume profile
- **Macro**: VIX, rates, sector rotation

---

## 📋 PLAN DE ACCIÓN (Orden de Prioridad)

### 🚀 Prioridad ALTA (Esta/próxima semana)

#### 1. Cambiar a horizonte intraday (day-trading)
```
Target: Predecir dirección en próxima 1-4 horas
Ventajas:
- Menos ruido macro
- Más samples (78 velas/día en 5m)
- Context más claro (opening, mid-day, close)

Script: 09d_make_features_intraday_hourly.py
```

#### 2. Redefinir target con magnitud
```python
# Opción A: Regresión
target = ret_fwd_5d  # Predecir return directamente

# Opción B: Multi-class
target = {
    2: ret > 3%,     # Strong up
    1: 0% < ret <= 3%,  # Weak up
    0: -3% <= ret < 0%,  # Weak down
    -1: ret < -3%    # Strong down
}

# Opción C: Adaptativo por ATR
threshold = ATR_14 * 1.5  # Dinámico por ticker
```

#### 3. Expandir universo de tickers
```
Objetivo: 50+ tickers líquidos
Incluir: Top 30 SPY + QQQ + sectores balanceados
Script: 19_build_ticker_universe.py (ya existe)
```

#### 4. Agregar fundamentals básicos
```
Features pendientes:
- P/E ratio (Yahoo Finance)
- Earnings date proximity
- Analyst ratings consensus
- Sector performance relativa

Script: 09e_add_fundamental_features.py (crear)
```

### 🔧 Prioridad MEDIA (2-4 semanas)

#### 5. Implementar purged K-Fold
```
TimeSeriesSplit básico → PurgedKFold
- Evita solapamiento temporal
- Embargo period entre train/test
- Mejor estimación de OOS

Librería: mlfinlab o implementación custom
```

#### 6. Feature importance y selección
```
- SHAP values por fold
- Eliminar features con importance < 0.01
- Detectar colinearidad (VIF > 5)
- Recursive Feature Elimination

Script: 09f_feature_selection_shap.py
```

#### 7. Hyperparameter tuning
```
- Optuna para RF/XGB/Cat
- Early stopping en XGB
- Max_depth, learning_rate, n_estimators

Script: 10c_hyperparam_tuning.py
```

### 📊 Prioridad BAJA (1-2 meses)

#### 8. Alternative ML approaches
```
- LightGBM (más rápido que XGB)
- TabNet (deep learning for tabular)
- Transformer-based (temporal patterns)
```

#### 9. Meta-features
```
- Embeddings de ticker (similar to Word2Vec)
- Regime embeddings
- Temporal embeddings (hour/day/month)
```

#### 10. Ensemble diversification
```
- Añadir Gradient Boosting alternativo
- Neural Network (MLP simple)
- Linear models con regularización (Lasso/Ridge)
```

---

## 🎯 OBJETIVOS REALISTAS (Revisados)

### Fase 1 (Próximos 7 días) - Target: AUC 0.58-0.60
- [ ] Implementar target intraday (1-4h horizon)
- [ ] Expandir a 50 tickers
- [ ] Agregar fundamentals básicos (P/E, earnings proximity)
- [ ] Re-entrenar con walk-forward

### Fase 2 (Semanas 2-4) - Target: AUC 0.60-0.62
- [ ] Feature selection con SHAP
- [ ] Purged K-Fold validation
- [ ] Hyperparameter tuning con Optuna
- [ ] Calibración por sector/régimen

### Fase 3 (Mes 2-3) - Target: AUC 0.62-0.65
- [ ] Alternativas de ML (LightGBM, TabNet)
- [ ] Meta-features avanzadas
- [ ] Sentiment analysis (optional)
- [ ] Microstructure features (si datos disponibles)

**Nota**: AUC 0.62-0.65 es **realista** para trading algorítmico en equities. 
Si llegamos a 0.60-0.62 **ya es explotable** con buena gestión de riesgo.

---

## ⚠️ WARNINGS Y BANDERAS ROJAS

### 1. No usar el modelo actual en producción
- AUC 0.555 → Apenas mejor que random
- Brier 0.36 → Peor que baseline (0.24)
- **Esperado P&L: Negativo** tras comisiones/slippage

### 2. Data leakage ya corregido, pero vigilar
- Siempre usar walk-forward o purged K-Fold
- NUNCA entrenar calibrador en mismo set que ensemble
- Verificar dates: train_end < test_start

### 3. Expectations realistas
- **ML no es magia**: Mercados son eficientes
- **Alpha decay**: Lo que funciona hoy, mañana no
- **Overhead costs**: Comisiones, slippage, market impact
- **Target mínimo viable**: AUC 0.60, Win Rate 55%, Sharpe > 1.0

### 4. Coverage vs Quality trade-off
- No sobre-optimizar para coverage alto
- Mejor: **20% coverage con 60% win rate**
- Que: **80% coverage con 52% win rate**

---

## 📈 MÉTRICAS DE ÉXITO (Finales)

**Para considerar el modelo "production-ready":**

| Métrica | Mínimo | Target | Excelente |
|---------|--------|--------|-----------|
| AUC OOS | 0.58 | 0.62 | 0.65+ |
| Brier OOS | < 0.25 | < 0.22 | < 0.20 |
| Win Rate | 55% | 58% | 62% |
| Sharpe (backtest) | 1.0 | 1.5 | 2.0+ |
| Max DD | < 20% | < 15% | < 10% |
| Coverage | 10-15% | 15-20% | 20-25% |

**Con métricas actuales:**
- AUC: 0.555 → **11% por debajo del mínimo**
- Brier: 0.362 → **45% peor que target**
- Estado: **REQUIERE TRABAJO ADICIONAL**

---

## 🔄 PRÓXIMOS COMANDOS A EJECUTAR

```powershell
# 1. Expandir tickers (prioridad #1)
python scripts\19_build_ticker_universe.py --min-volume 1000000 --max-tickers 50

# 2. Re-descargar datos históricos
python scripts\00_download_daily.py --start-date 2020-01-01

# 3. Regenerar features
python scripts\09_make_features_daily.py
python scripts\09c_add_context_features.py

# 4. Crear features intraday
python scripts\09d_make_features_intraday_hourly.py

# 5. Agregar fundamentals
python scripts\09e_add_fundamental_features.py

# 6. Re-entrenar con walk-forward
python scripts\10_train_direction_ensemble_WALKFORWARD.py

# 7. Validar métricas
python scripts\validate_model_quality.py
```

---

## 💡 LECCIONES APRENDIDAS

1. **Siempre validar OOS primero** antes de celebrar métricas
2. **Data leakage es sutil** pero devastador
3. **Features técnicas solas no bastan** para alpha sostenible
4. **Más datos > mejores algoritmos** en early stages
5. **Horizonte temporal importa**: Intraday > daily para predictibilidad

---

**Status Final**: ⚠️ TRABAJO EN PROGRESO - NO LISTO PARA TRADING REAL

**Recomendación**: Seguir plan de acción (Fases 1-3) antes de evaluar viabilidad productiva.
