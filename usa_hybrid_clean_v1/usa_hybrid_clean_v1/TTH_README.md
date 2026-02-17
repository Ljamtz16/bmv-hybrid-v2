# Time-to-Hit (TTH) - Sistema de Predicción de Tiempo hasta TP/SL

## 📖 Descripción

Sistema avanzado que predice **cuándo** (no solo si) se alcanzará el Take Profit o Stop Loss. Utiliza tres enfoques:

1. **Hazard Discreto** (día a día) - Random Forest por día
2. **Monte Carlo** (GBM calibrado) - Simulaciones probabilísticas
3. **Supervivencia** (opcional) - Cox / Random Survival Forest

---

## 🎯 Métricas que Predice

Para cada señal de trading, el sistema calcula:

### Probabilidades Temporales:
- `p_tp_in_1d` - Probabilidad de alcanzar TP en ≤1 día
- `p_tp_in_2d` - Probabilidad de alcanzar TP en ≤2 días
- `p_tp_in_3d` - Probabilidad de alcanzar TP en ≤3 días
- `p_sl_in_1d`, `p_sl_in_2d`, `p_sl_in_3d` - Ídem para SL

### Tiempos Esperados:
- `etth_tp` - Expected Time-to-Hit TP (días)
- `etth_sl` - Expected Time-to-Hit SL (días)
- `etth_first_event` - Tiempo esperado al primer evento (TP o SL)

### Probabilidades de Orden:
- `p_tp_before_sl` - P(TP ocurre antes que SL)
- `tth_score` - Score compuesto 0-100 para ranking

---

## 🚀 Instalación y Setup

### 1. Instalar Dependencias Adicionales

```powershell
pip install scikit-survival pyarrow
```

### 2. Generar Datos de Entrenamiento

Primero necesitas **historial de trades** de meses anteriores:

```powershell
# Etiquetar trades históricos
python scripts/37_label_time_to_event.py --months "2025-01,2025-02,2025-03,2025-04,2025-05,2025-06,2025-07,2025-08,2025-09,2025-10"
```

**Output:** `data/trading/time_to_event_labeled.parquet`

Esto genera:
- `time_to_event_days` - Días hasta TP/SL/censura
- `event_type` - TP, SL, CENSORED
- `event_observed` - 1 si evento, 0 si censura
- Features al momento de la señal

### 3. Entrenar Modelos TTH

```powershell
# Entrenar hazard discreto + Monte Carlo
python scripts/38_train_time_to_hit.py --max-days 5
```

**Output:**
- `models/tth_hazard_discrete.joblib` - Modelos por día (TP y SL)
- `models/tth_monte_carlo.joblib` - Calibración MC
- `models/tth_metadata.json` - Metadatos

---

## 📊 Uso en Producción

### Opción 1: Predecir TTH para Señales Existentes

```powershell
# Añadir columnas TTH a forecast
python scripts/39_predict_time_to_hit.py `
  --input reports/forecast/2025-10/forecast_with_patterns.csv `
  --output reports/forecast/2025-10/forecast_with_patterns_tth.csv `
  --use-mc
```

### Opción 2: Generar Trade Plan con TTH

```powershell
# Plan optimizado con ranking TTH
python scripts/40_make_trade_plan_with_tth.py `
  --input reports/forecast/2025-10/forecast_with_patterns_tth.csv `
  --strategy balanced `
  --max-signals 15 `
  --min-p-tp-before-sl 0.60 `
  --max-etth 2.5
```

**Output:**
- `trade_plan_tth.csv` - Plan con scores TTH
- `trade_plan_tth_telegram.txt` - Mensajes formateados
- `trade_plan_tth_stats.json` - Estadísticas agregadas

---

## 🎨 Estrategias de Ranking

### `--strategy fast` (Rotación Rápida)
Prioriza señales con **ETTH bajo**:
```
Score = -0.4*ETTH + 0.3*P(TP≺SL) + 0.2*prob_win + 0.1*|y_hat|
```
**Uso:** Day trading, alta rotación

### `--strategy quality` (Alta Confianza)
Prioriza **P(TP antes que SL)**:
```
Score = 0.4*P(TP≺SL) + 0.3*prob_win - 0.2*ETTH + 0.1*|y_hat|
```
**Uso:** Swing trading, menor frecuencia

### `--strategy balanced` (Default)
Balance entre velocidad y calidad:
```
Score = 0.3*P(TP≺SL) - 0.3*ETTH + 0.25*prob_win + 0.15*|y_hat|
```

---

## 📈 Integración con Pipeline

### Modificar `run_pipeline_usa.ps1`

Añade al final del pipeline:

```powershell
# === Time-to-Hit Prediction ===
if (Test-Path "models\tth_hazard_discrete.joblib") {
    Write-Host "=== Prediciendo Time-to-Hit ==="
    & $PY scripts/39_predict_time_to_hit.py `
        --input "reports/forecast/$Month/forecast_with_patterns.csv" `
        --use-mc
    
    Write-Host "=== Generando Trade Plan con TTH ==="
    & $PY scripts/40_make_trade_plan_with_tth.py `
        --input "reports/forecast/$Month/forecast_with_patterns_tth.csv" `
        --strategy balanced `
        --max-signals 15
} else {
    Write-Host "[WARN] Modelos TTH no encontrados, ejecuta 37 y 38 primero"
}
```

---

## 📱 Formato Telegram

Ejemplo de mensaje generado:

```
#1 · AMD · BUY
TP 6.0% · SL 0.15% · H=3D
━━━━━━━━━━━━━━━━━━━━━
📊 Probabilidades:
  • P(win) = 78%
  • P(TP≤1D) = 35%
  • P(TP≤3D) = 68%
  • P(TP≺SL) = 72%

⏱ Time-to-Hit:
  • ETTH(TP) = 2.1 días
  • Score = 85/100
```

---

## 🔧 Filtros Recomendados

### Para Rotación Rápida:
```powershell
--max-etth 2.0 --min-p-tp-before-sl 0.65 --strategy fast
```

### Para Alta Calidad:
```powershell
--max-etth 3.0 --min-p-tp-before-sl 0.70 --strategy quality
```

### Para Balance:
```powershell
--max-etth 2.5 --min-p-tp-before-sl 0.60 --strategy balanced
```

---

## 📊 Evaluación y Calibración

### Evaluar Predicciones Pasadas

```powershell
# Comparar TTH predicho vs. real
python scripts/41_calibrate_tth.py --month 2025-10
```

Esto genera:
- **Reliability plots** - P(TP≤k) predicho vs. observado
- **MAE de ETTH** - Error absoluto medio
- **Calibración por decil** - Score vs. tasa de acierto

### Métricas de Calibración:
- **Brier Score** para probabilidades
- **MAE** para ETTH
- **Discrimination** (AUC) para P(TP≺SL)

---

## 🎯 Casos de Uso

### 1. Priorizar Señales por Velocidad
```python
# Top 10 señales con ETTH más bajo
df_fast = df[df['etth_first_event'] <= 2.0].nlargest(10, 'tth_score')
```

### 2. Filtrar por Alta Probabilidad TP
```python
# Señales con >70% probabilidad de TP antes que SL
df_quality = df[df['p_tp_before_sl'] >= 0.70]
```

### 3. Detectar Señales "Inmediatas"
```python
# Alta probabilidad de TP en 1 día
df_immediate = df[df['p_tp_in_1d'] >= 0.40]
```

### 4. Evitar Señales Lentas
```python
# Descartar señales con ETTH > 3.5 días
df_filtered = df[df['etth_first_event'] <= 3.5]
```

---

## 🧪 Monte Carlo: Parámetros

### Calibración Automática:
- **μ (drift)** = f(y_hat, horizon_days) - Retorno esperado por día
- **σ (volatilidad)** = f(ATR%, vol_z) - Volatilidad diaria

### Simulación:
- **N simulaciones** = 1000 (default)
- **Steps per day** = 26 (intraday resolution)
- **Proceso** = GBM (Geometric Brownian Motion)

### Fórmulas:
```
dS/S = μ*dt + σ*dW
ETTH ≈ Δ/μ (primer orden)
P(TP antes que SL) = función de μ, σ, barriers
```

---

## 📈 Mejoras Futuras

### 1. Riesgos Competitivos
Modelar TP y SL simultáneamente con **Competing Risks**:
```python
from sksurv.ensemble import RandomSurvivalForest
# Entrenar modelo con event_type como outcome
```

### 2. Datos Intradía
Si tienes datos de 15m/1h:
```python
# Hazard por barra intradía
steps_per_day = 26  # 6.5h * 4 barras/h
```

### 3. Features Adicionales
- **Spread** - bid/ask spread
- **Order flow** - volumen comprador vs. vendedor
- **Market regime** - VIX, sector rotation

### 4. Deep Learning
```python
# LSTM para secuencias de hazard
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
```

---

## ⚠️ Notas Importantes

### Censura Correcta:
- **NO** llames "SL" a trades que expiraron sin tocar
- Usa `event_observed = 0` para censura
- Importante para calibración

### Validación:
- **Backtest** con datos out-of-sample
- **Walk-forward** mensual
- **Calibration plots** obligatorios

### Limitaciones:
- Requiere **historial suficiente** (≥3 meses, ≥50 trades)
- **No** predice eventos de cisne negro
- Asume **continuidad** de precio (gaps limitados)

---

## 📚 Referencias

### Papers:
- Karatzas & Shreve (1998) - *Brownian Motion and Stochastic Calculus*
- Cox (1972) - *Regression Models and Life-Tables*
- Ishwaran et al. (2008) - *Random Survival Forests*

### Bibliotecas:
- `scikit-survival` - Survival analysis en Python
- `lifelines` - Cox PH, Kaplan-Meier
- `pycox` - Deep learning survival

---

## 🆘 Troubleshooting

### Error: "No se encuentran modelos TTH"
```powershell
# Entrenar modelos primero
python scripts/37_label_time_to_event.py
python scripts/38_train_time_to_hit.py
```

### Error: "Datos insuficientes"
```powershell
# Necesitas al menos 3 meses de historia
# Añade más meses al etiquetado
python scripts/37_label_time_to_event.py --months "2025-01,2025-02,...,2025-10"
```

### Warning: "Hazard día X skip"
Normal si hay pocos eventos en ese día. El modelo usa días disponibles.

### Calibración pobre
- Añadir más features (spread, vol intradía)
- Aumentar historial (6+ meses)
- Revisar censura correcta

---

## 📞 Contacto y Soporte

Para más información sobre TTH:
- Revisar `scripts/37_label_time_to_event.py` (comentarios)
- Revisar `scripts/38_train_time_to_hit.py` (algoritmos)
- Revisar `scripts/39_predict_time_to_hit.py` (inferencia)

**Autor:** USA Hybrid Clean V1 + TTH Extension  
**Versión:** 1.0  
**Fecha:** Noviembre 2025
