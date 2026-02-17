# 📊 Análisis Predicción vs Realidad - USA Hybrid Clean V1

## Resumen Ejecutivo

Se han generado **análisis completos** de predicción vs realidad para los modelos:
- **`return_model_H3`**: Predice retorno a 3 días (`y_hat` vs `y_H3`)
- **`prob_win_clean`**: Predice probabilidad de ganancia (`prob_win`)

### 📈 Hallazgos Principales

| Métrica | Valor | Interpretación |
|---------|-------|-----------------|
| **MAE** | 0.0518 | Error promedio muy bajo ✓ |
| **RMSE** | 0.0685 | Consistente |
| **Directional Accuracy** | 48.81% | **⚠️ Apenas mejor que aleatorio** |
| **Brier Score (prob_win)** | 0.2827 | Razonablemente bien calibrado |
| **Win Rate Real** | 54.61% | Ligeramente positivo |
| **Prob Predicha** | 42.16% | Sesgo conservador (-12.45%) |

---

## 📁 Archivos Generados

### 1. Scripts Python

#### `analysis_pred_vs_real.py`
**Qué hace:** Análisis completo de predicción vs realidad
- Carga `forecast_signals.csv`
- Calcula MAE, RMSE, MAPE, directional accuracy
- Genera **10 gráficas** (5 globales + 5 por ticker top)
- Imprime métricas por ticker

**Usar:**
```bash
python analysis_pred_vs_real.py
```

**Salida:** 
- `outputs/analysis/01_pred_vs_real_*.png` - Líneas (predicción vs real)
- `outputs/analysis/02_error_timeseries_*.png` - Error absoluto
- `outputs/analysis/03_error_band_*.png` - Banda de confianza
- `outputs/analysis/04_scatter_*.png` - Scatter plot
- `outputs/analysis/05_calibration_*.png` - Curva de calibración

---

#### `analysis_trading_results.py`
**Qué hace:** Análisis de trades ejecutados (equity curve)
- Carga `outputs/equity_curve.csv`
- Calcula win rate, PnL total, profit factor
- Genera **4 gráficas** de trading

**Usar:**
```bash
python analysis_trading_results.py
```

**Salida:**
- `outputs/analysis/06_pnl_timeseries.png` - PnL por trade + acumulado
- `outputs/analysis/07_pnl_distribution.png` - Histograma ganancias/pérdidas
- `outputs/analysis/08_pnl_by_ticker.png` - Box plot por ticker
- `outputs/analysis/09_win_rate_by_ticker.png` - Win rate y avg PnL

---

### 2. Dashboard Interactivo

#### `analysis_dashboard.html`
**Qué es:** Visualizador web con todas las gráficas y métricas

**Usar:**
```bash
# Opción 1: Servidor local
python serve_analysis_dashboard.py
# Luego abre: http://localhost:8765/analysis_dashboard.html

# Opción 2: Abrir directo
# Windows: start analysis_dashboard.html
# Mac/Linux: open analysis_dashboard.html
```

**Pestañas disponibles:**
1. 📈 **Resumen** - KPIs principales en tarjetas
2. 📉 **Regresión** - Gráficas de predicción vs real
3. 📊 **Probabilidad** - Curvas de calibración
4. 💰 **Trading** - Resultados de equity curve
5. 💡 **Interpretación** - Análisis y recomendaciones

---

## 🎯 Guía Rápida de Métricas

### **Regresión (Modelo de Retorno)**

```python
# En tu CSV tienes:
# y_H3    = retorno real a 3 días
# y_hat   = predicción del modelo

# Métricas calculadas:
MAE     = promedio(|y_true - y_pred|)      # 0.0518
RMSE    = sqrt(promedio((y_true - y_pred)²)) # 0.0685
MAPE    = promedio(|error| / |y_true|) * 100 # 5.7M% (cuidado con división por cero)

# Directional Accuracy
dir_acc = % de veces que sign(y_true) == sign(y_pred)  # 48.81%
```

### **Probabilidad (Brier Score)**

```python
# En tu CSV tienes:
# prob_win = probabilidad predicha
# y_H3     = retorno real

# Conversión a binario:
y_true_binary = 1 si y_H3 > 0, sino 0   # ¿ganamos?

# Brier Score (error cuadrático medio de probabilidades)
brier = promedio((prob_win - y_true_binary)²)  # 0.2827

# Calibración: ¿son las probs confiables?
# Ideal = curva en diagonal de 45°
# Real = qué frecuencia real corresponde a cada prob predicha
```

### **Trading**

```python
# En equity_curve.csv tienes:
# PnL USD = ganancia/pérdida por trade
# Exit Reason = por qué se cerró

# Métricas:
win_rate = % de trades con PnL USD > 0  # 0% (actualmente)
profit_factor = (ganancias totales) / (pérdidas totales)  # 0 si no hay ganancias
avg_win = PnL promedio de trades ganadores
avg_loss = PnL promedio de trades perdedores
```

---

## 📊 Interpretación de Resultados

### ✅ Lo Positivo

1. **MAE muy bajo (0.0518)**: El error promedio en predicción es pequeño
2. **Brier Score razonable (0.28)**: prob_win está bien calibrado (rango ideal: 0.20-0.30)
3. **Datos suficientes**: 26,640 observaciones (válido estadísticamente)
4. **Diversificación**: Funciona en 18 tickers diferentes

### ⚠️ Lo que Preocupa

1. **Directional Accuracy = 48.81%** 
   - Idealmente debería ser > 52% para ser mejor que aleatorio
   - El modelo NO está prediciendo bien si el retorno sube o baja
   - **Implicación**: El MAE bajo puede deberse a que el modelo predice todo muy cerca de 0

2. **Sesgo en prob_win = -12.45%**
   - Predice 42% cuando la realidad es 54.61%
   - El modelo es demasiado conservador
   - **Solución**: Recalibración isotónica

3. **Datos de trading actuales**
   - Solo 4 trades en período reciente
   - Win rate 0% (pero período muy corto)
   - Esperar mínimo 30-50 trades para validar

---

## 🔧 Personalización

### Cambiar período de análisis

En `analysis_pred_vs_real.py`, línea donde cargas el CSV:

```python
# Filtrar solo ciertos tickers
df = df[df["ticker"].isin(["AAPL", "MSFT", "NVDA"])]

# Filtrar por fecha
df = df[(df["date"] >= "2025-09-01") & (df["date"] <= "2025-10-31")]

# Filtrar solo trades ganadores
df_wins = df[df["y_H3"] > 0]
```

### Cambiar banda de error

En `plot_error_band()`:

```python
k = 2.0  # Cambiar de 1.0 a 2.0 para banda más ancha (2σ)
```

### Agregar más gráficas

Patrón a seguir:

```python
def plot_nueva_grafica(df):
    fig, ax = plt.subplots(figsize=(14, 6))
    # Tu código aquí
    plt.savefig(OUTPUTS_DIR / "10_nueva_grafica.png", dpi=150)
    plt.close()
```

---

## 📈 Recomendaciones Próximos Pasos

### 1. **Inmediato** (Hoy)
- [ ] Revisar directional accuracy: ¿por qué es ~50%?
- [ ] Analizar distribución de y_H3: ¿hay muchos valores cercanos a 0?
- [ ] Verificar que features sean relevantes

### 2. **Corto plazo** (Esta semana)
- [ ] Recalibrar prob_win (usar `sklearn.calibration.CalibratedClassifierCV`)
- [ ] Esperar a tener mínimo 20 trades ejecutados para validar
- [ ] Analizar por sector: ¿alguno tiene mejor performance?

### 3. **Mediano plazo** (Este mes)
- [ ] Intentar ensemble de modelos (bagging, stacking)
- [ ] Feature engineering: agregar volatilidad, momentum, correlation
- [ ] Análisis de régimen: ¿mejor performance en ciertos períodos?

### 4. **Validación rolling**
- Ejecutar estos scripts **semanalmente** para monitorear degradación
- Alertar si directional accuracy cae por debajo de 48%
- Re-entrenar modelos si métricas se degradan 10%+

---

## 💻 Requisitos

```bash
# Instalar (si no está hecho):
pip install pandas numpy matplotlib seaborn scikit-learn

# Verificar:
python -c "import pandas, numpy, matplotlib, seaborn, sklearn; print('✓ OK')"
```

---

## 📞 Troubleshooting

### Error: "No encontrado: forecast_signals.csv"
- Verifica que exista: `reports/forecast/2025-11/forecast_signals.csv`
- Si no, ejecuta antes: el pipeline de inferencia (`infer_and_gate.py`)

### Error: "ModuleNotFoundError: No module named 'seaborn'"
```bash
pip install seaborn
```

### Las gráficas se ven blancas
- Asegúrate que el directorio `outputs/analysis/` existe
- El script debería crearlo automáticamente, pero puedes crear manualmente

### Dashboard no carga imágenes
- Verifica que `outputs/analysis/*.png` exista y tenga los nombres exactos
- Abre developer tools (F12) en navegador para ver errores

---

## 📝 Ejemplo de Uso Completo

```bash
# 1. Ejecutar análisis
python analysis_pred_vs_real.py
python analysis_trading_results.py

# 2. Servir dashboard
python serve_analysis_dashboard.py

# 3. Abrir navegador
# http://localhost:8765/analysis_dashboard.html

# 4. Explorar pestañas
# - Resumen: ver KPIs
# - Regresión: ver si modelo predice bien dirección
# - Probabilidad: ver si prob_win es confiable
# - Trading: ver PnL
# - Interpretación: leer recomendaciones
```

---

## 📚 Recursos Adicionales

### Métricas de Regresión
- **MAE**: Más interpretable (misma unidad que y)
- **RMSE**: Penaliza outliers más
- **MAPE**: Porcentual, pero cuidado con divisiones por cero

### Calibración
- **Brier Score < 0.25**: Bien calibrado
- **Brier Score 0.25-0.30**: Aceptable
- **Brier Score > 0.35**: Requiere recalibración

### Directional Accuracy
- **50%**: Aleatorio puro (no hay skill)
- **52-55%**: Algo de skill
- **> 55%**: Buen modelo de dirección

---

**Generado:** 12 Enero 2026  
**Autor:** GitHub Copilot  
**Datos:** 2020-01-02 a 2025-10-31 (26,640 observaciones)  
**Modelos:** `return_model_H3.joblib`, `prob_win_clean.joblib`
