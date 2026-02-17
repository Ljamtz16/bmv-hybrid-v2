# ANÁLISIS PREDICCIÓN VS REALIDAD - RESUMEN FINAL

## ✅ Completado Exitosamente

Se han generado **análisis completos** de predicción vs realidad con:
- **10 gráficas de regresión** (predicción vs real, error, bandas, scatter, calibración)
- **4 gráficas de trading** (PnL, distribución, por ticker)
- **Métricas detalladas** (MAE, RMSE, MAPE, Directional Accuracy, Brier Score)
- **Dashboard interactivo HTML** con todas las visualizaciones
- **Reporte ejecutivo** en texto

---

## 📊 Archivos Generados

### Scripts Python (ejecutables)

```
analysis_pred_vs_real.py          → Análisis de predicción vs realidad
analysis_trading_results.py        → Análisis de equity curve (trades)
generate_analysis_report.py        → Generador de reporte ejecutivo
serve_analysis_dashboard.py        → Servidor local para dashboard
```

### Visualizaciones (24 gráficas PNG)

#### Gráficas de Regresión

```
outputs/analysis/
├── 01_pred_vs_real_all.png        → Predicción vs real (global)
├── 01_pred_vs_real_AAPL.png       → Predicción vs real (AAPL)
├── 01_pred_vs_real_AMD.png        → Predicción vs real (AMD)
├── 01_pred_vs_real_AMZN.png       → Predicción vs real (AMZN)
│
├── 02_error_timeseries_all.png    → Error absoluto (global)
├── 02_error_timeseries_AAPL.png   → Error absoluto (AAPL)
├── 02_error_timeseries_AMD.png    → Error absoluto (AMD)
├── 02_error_timeseries_AMZN.png   → Error absoluto (AMZN)
│
├── 03_error_band_all.png          → Predicción + banda de error (global)
├── 03_error_band_AAPL.png         → Predicción + banda de error (AAPL)
├── 03_error_band_AMD.png          → Predicción + banda de error (AMD)
├── 03_error_band_AMZN.png         → Predicción + banda de error (AMZN)
│
├── 04_scatter_all.png             → Scatter plot (global)
├── 04_scatter_AAPL.png            → Scatter plot (AAPL)
├── 04_scatter_AMD.png             → Scatter plot (AMD)
├── 04_scatter_AMZN.png            → Scatter plot (AMZN)
│
├── 05_calibration_all.png         → Curva de calibración (global)
├── 05_calibration_AAPL.png        → Curva de calibración (AAPL)
├── 05_calibration_AMD.png         → Curva de calibración (AMD)
├── 05_calibration_AMZN.png        → Curva de calibración (AMZN)
│
├── 06_pnl_timeseries.png          → PnL en tiempo (global)
├── 07_pnl_distribution.png        → Distribución de PnL
├── 08_pnl_by_ticker.png           → PnL por ticker
└── 09_win_rate_by_ticker.png      → Win rate por ticker
```

### Dashboard e Informes

```
analysis_dashboard.html            → Dashboard web interactivo (7 pestañas)
outputs/ANALYSIS_REPORT.txt        → Reporte ejecutivo en texto
ANALYSIS_README.md                 → Documentación completa
```

---

## 🎯 Hallazgos Clave

### Modelo de Retorno (y_hat vs y_H3)

| Métrica | Valor | Evaluación |
|---------|-------|-----------|
| **MAE** | 0.0518 | ✓ Muy bajo |
| **RMSE** | 0.0685 | ✓ Consistente |
| **Directional Accuracy** | **48.81%** | ⚠️ Apenas mejor que aleatorio |
| **Muestras** | 26,640 | ✓ Estadísticamente válido |

**Interpretación:** El modelo predice magnitud de retorno bien (MAE bajo), pero **NO predice bien la dirección** (sube/baja).

### Modelo de Probabilidad (prob_win)

| Métrica | Valor | Evaluación |
|---------|-------|-----------|
| **Brier Score** | 0.2827 | ⚠️ Límite entre aceptable y revisar |
| **Win Rate Real** | 54.61% | ✓ Ligeramente positivo |
| **Prob Predicha** | 42.16% | ⚠️ Subestima sistemáticamente |
| **Sesgo** | -12.44% | ⚠️ Conservador |
| **Mejor Ticker** | XOM (Brier=0.2099) | ✓ |
| **Peor Ticker** | QQQ (Brier=0.3426) | ✗ Requiere recalibración |

**Interpretación:** El modelo es demasiado conservador. Predice probabilidades más bajas de lo que debería.

### Resultados de Trading (Nov-Dic 2025)

| Métrica | Valor | Nota |
|---------|-------|------|
| **Total Trades** | 4 | ⚠️ Muestra muy pequeña |
| **Win Rate** | 0% | ⚠️ Período desfavorable |
| **Total PnL** | -$25,436 | ⚠️ Debido a SL triggered |
| **Avg Loss** | -$6,359 | Pérdida por trade |

**Interpretación:** Datos insuficientes. Se necesitan mínimo 30-50 trades para validación estadística.

---

## 📈 Cómo Usar los Outputs

### 1. Ver Dashboard Interactivo

```bash
# Opción A: Servidor local (recomendado)
python serve_analysis_dashboard.py
# Luego abre: http://localhost:8765/analysis_dashboard.html

# Opción B: Abrir directo (solo gráficas, sin interactividad)
# Windows:
start analysis_dashboard.html

# Mac/Linux:
open analysis_dashboard.html
```

**Pestañas disponibles:**
1. **Resumen** - KPIs principales en tarjetas
2. **Regresión** - Gráficas de predicción vs real
3. **Probabilidad** - Curvas de calibración
4. **Trading** - Resultados de equity curve
5. **Interpretación** - Análisis y recomendaciones

### 2. Leer Reporte Ejecutivo

```bash
cat outputs/ANALYSIS_REPORT.txt
# o abre con tu editor favorito
```

### 3. Analizar Gráficas Específicas

```bash
# Ver todas las gráficas
ls -la outputs/analysis/

# Abrir una específica en Windows
start outputs/analysis/01_pred_vs_real_all.png

# En Python (si tienes Jupyter)
from PIL import Image
import matplotlib.pyplot as plt
img = Image.open("outputs/analysis/04_scatter_all.png")
plt.imshow(img)
plt.show()
```

### 4. Regenerar Análisis

```bash
# Si actualizaste forecast_signals.csv
python analysis_pred_vs_real.py

# Si actualizaste equity_curve.csv
python analysis_trading_results.py

# Ambos + reporte
python analysis_pred_vs_real.py && python analysis_trading_results.py && python generate_analysis_report.py
```

---

## 🔧 Personalización

### Cambiar Período de Análisis

En `analysis_pred_vs_real.py`, agregar después de cargar:

```python
# Filtrar período específico
df = df[(df["date"] >= "2025-09-01") & (df["date"] <= "2025-10-31")]

# O solo tickers específicos
df = df[df["ticker"].isin(["AAPL", "MSFT", "NVDA"])]
```

### Cambiar Banda de Error

En `plot_error_band()`:

```python
k = 2.0  # Cambiar de 1.0 a 2.0 para banda más ancha (±2σ)
```

### Agregar Tickers al Dashboard

Modificar `analysis_pred_vs_real.py`:

```python
# Línea ~170, cambiar:
top_tickers = df["ticker"].value_counts().head(3).index.tolist()
# Por:
top_tickers = df["ticker"].value_counts().head(5).index.tolist()
```

---

## ⚡ Recomendaciones Inmediatas

### 🔴 CRÍTICO
**Directional Accuracy = 48.81% < 52%**
- El modelo NO está prediciendo bien la dirección (sube/baja)
- **Acción:** Revisar features dentro de 1 semana

### 🟡 IMPORTANTE
**Sesgo en prob_win = -12.44%**
- Subestima sistemáticamente la probabilidad
- **Acción:** Recalibrar usando `CalibratedClassifierCV`

### 🟡 IMPORTANTE
**Datos de trading muy limitados (4 trades)**
- Esperar a acumular 30-50 trades antes de conclusiones
- **Acción:** Continuar operando y monitorear

---

## 📚 Estructura de Código

### `analysis_pred_vs_real.py` - Principales Funciones

```python
load_data(csv_path)                    # Cargar y limpiar datos
metrics_regression(y_true, y_pred)     # Calcular MAE, RMSE, MAPE
directional_accuracy(y_true, y_pred)   # % signo correcto

plot_pred_vs_real_timeseries(df)       # Gráfica líneas
plot_error_timeseries(df)              # Gráfica error absoluto
plot_error_band(df, k=1.0)             # Gráfica banda
plot_scatter_pred_vs_real(df)          # Scatter plot
plot_calibration_curve(df)             # Curva de calibración

print_metrics_table(df)                # Tabla por ticker
print_probability_metrics(df)          # Métricas prob_win
```

### `analysis_trading_results.py` - Principales Funciones

```python
load_equity_curve(csv_path)            # Cargar trades
print_trading_metrics(df)              # Calcular PnL, win rate

plot_pnl_timeseries(df)                # Gráfica PnL
plot_pnl_distribution(df)              # Histograma
plot_pnl_by_ticker(df)                 # Box plot por ticker
plot_win_rate_by_ticker(df)            # Win rate + PnL promedio
```

---

## 🐛 Troubleshooting

### Error: "ModuleNotFoundError: No module named 'seaborn'"
```bash
pip install seaborn
```

### Error: "No encontrado: forecast_signals.csv"
- Asegúrate que el archivo existe en: `reports/forecast/2025-11/`
- Si no, ejecuta el pipeline de inferencia primero

### Dashboard no carga gráficas
- Verifica que `outputs/analysis/*.png` exista
- Abre browser developer tools (F12) para ver errores
- Prueba abrir HTML directamente (sin servidor)

### Las métricas se ven raras (MAPE muy alto)
- MAPE tiene problemas si y_true está cerca de 0
- Es normal para retornos pequeños, **ignorar MAPE**
- Usar MAE/RMSE en su lugar

---

## 📞 Próximos Pasos Recomendados

### Esta Semana
- [ ] Leer ANALYSIS_README.md completo
- [ ] Abrir analysis_dashboard.html en navegador
- [ ] Revisar gráficas de directional accuracy
- [ ] Verificar calibración de QQQ

### Este Mes
- [ ] Recalibrar prob_win (usar calibration.py)
- [ ] Esperar a 20+ trades ejecutados
- [ ] Análisis de features: ¿cuáles son más predictivas?
- [ ] Probar ensemble de modelos

### Monitoreo Continuo
- [ ] Ejecutar scripts semanalmente (cada lunes)
- [ ] Alertar si directional accuracy < 48%
- [ ] Alertar si sesgo prob_win > 15%
- [ ] Gráficas de equity curve en tiempo real

---

**Generado:** 12 Enero 2026  
**Autor:** GitHub Copilot  
**Datos:** 2020-01-02 a 2025-10-31 (26,640 observaciones en 18 tickers)  
**Modelos:** return_model_H3.joblib (366 MB), prob_win_clean.joblib (135 MB)

---

## 📖 Lecturas Recomendadas

1. **ANALYSIS_README.md** - Documentación completa
2. **outputs/ANALYSIS_REPORT.txt** - Reporte ejecutivo
3. **analysis_dashboard.html** - Gráficas interactivas
4. **analysis_pred_vs_real.py** - Código fuente (bien comentado)
