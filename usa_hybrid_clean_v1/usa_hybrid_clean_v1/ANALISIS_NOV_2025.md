# Análisis Noviembre 2025 - USA Hybrid Clean V1

**Fecha de análisis:** 2 de noviembre de 2025  
**Sistema:** Trading automatizado con ML + Patrones técnicos

---

## 📈 Estado del Sistema

### ✅ Configuración Completada
- **Python:** 3.12.6
- **Entorno Virtual:** Recreado y funcional
- **Dependencias:** Todas instaladas
  - pandas 2.3.3
  - numpy 2.3.4
  - scikit-learn 1.7.2
  - yfinance 0.2.66
  - joblib 1.5.2

### 📊 Datos Disponibles
- **Período:** 2020-01-02 a 2025-10-31
- **Registros:** 26,406 datos históricos OHLCV
- **Tickers:** 18 del universo master

#### Distribución de Tickers por Sector:
- **Tecnología (4):** AAPL, MSFT, NVDA, AMD
- **Financieros (3):** JPM, GS, MS
- **Energía (2):** XOM, CVX
- **Defensivos (4):** KO, PG, WMT, JNJ
- **Otros (5):** AMZN, TSLA, META, GOOGL, NFLX

---

## 🔄 Pipeline Ejecutado

### Comando:
```powershell
.\scripts\run_pipeline_usa.ps1 -Month "2025-10" -Universe master -AutoTune
```

### Flujo de Procesamiento:
1. ✓ **Descarga de Precios** - Yahoo Finance (18 tickers)
2. ✓ **Generación de Features** - Indicadores técnicos
   - EMA 10/20
   - RSI 14
   - ATR 14
   - Volatilidad Z-score
3. ⏳ **Entrenamiento de Modelos** - Random Forest (en progreso)
   - return_model_H3 (predicción de retornos)
   - prob_win_clean (probabilidad de éxito)
4. ⏳ **Generación de Predicciones** - Horizonte 3-5 días
5. ⏳ **Detección de Patrones** - Análisis técnico
   - Double Top/Bottom
   - Patrones de continuación
6. ⏳ **Simulación de Trading** - Monte Carlo
7. ⏳ **Optimización (AutoTune)** - Búsqueda de umbrales óptimos
   - Target: 10-15 trades mensuales
   - Maximizar win rate y P&L

---

## 🎯 Parámetros de Política

### Configuración Base (Policy_Base.json):
- **Gate Threshold:** 0.57 → 0.54 (fallback)
- **Min Probability:** 0.56 → 0.54 (fallback)
- **Min Abs Y_hat:** 0.05
- **Take Profit:** 6%
- **Stop Loss:** 0.15%
- **Horizonte:** 3 días (dinámico con ATR)
- **Capital por Trade:** $200
- **Max Posiciones Abiertas:** 5 (guardrail: 2-5)
- **Cooldown:** 0 días
- **Capital Total Cap:** $1,000

### Guardrails de Seguridad:
- `2 <= max_open <= 5`
- `per_trade_cash * max_open <= 1000`
- Fallback automático si trades < 10

---

## 📁 Archivos Generados

Los resultados se guardarán en: `reports/forecast/2025-10/`

### Archivos Principales:
- `forecast_signals.csv` - Señales brutas del modelo ML
- `forecast_with_patterns.csv` - Señales + análisis de patrones
- `simulate_results_all.csv` - Trades simulados (todos)
- `simulate_results_sector_*.csv` - Trades por sector
- `kpi_all.json` - KPIs del portafolio global
- `kpi_compare_sectors.csv` - Comparación de sectores
- `Policy_Resolved.json` - Política final aplicada
- `autotune_choice.json` - Resultados de optimización
- `trades_detailed.csv` - Detalle de cada trade
- `activity_metrics.json` - Métricas de actividad

---

## 📊 KPIs Objetivo

### Métricas de Desempeño:
- **Trades Mensuales:** 10-15 (target)
- **Win Rate:** > 50%
- **P&L Neto:** Positivo
- **Capital Final:** > $1,100 (meta: +10%)
- **Drawdown Máximo:** < 5%

### Por Sector:
- **Tech:** Cap 70%
- **Defensive:** Cap 40%
- **Financials:** Cap 40%
- **Energy:** Cap 30%

---

## 🚀 Próximos Pasos (Después del Pipeline)

1. **Revisar KPIs:**
   ```powershell
   Get-Content reports\forecast\2025-10\kpi_all.json | ConvertFrom-Json
   ```

2. **Ver Trades Generados:**
   ```powershell
   Import-Csv reports\forecast\2025-10\simulate_results_all.csv | Format-Table
   ```

3. **Comparar Sectores:**
   ```powershell
   Import-Csv reports\forecast\2025-10\kpi_compare_sectors.csv | Format-Table
   ```

4. **Generar Plan de Trading:**
   ```powershell
   python scripts/33_make_trade_plan.py --month 2025-10
   ```

5. **Enviar Notificaciones (opcional):**
   ```powershell
   python scripts/34_send_trade_plan_to_telegram.py --month 2025-10
   ```

---

## ⚠️ Notas Importantes

### Limitaciones Detectadas:
1. **Datos Históricos vs Predicción:**
   - Los datos son hasta octubre 31, 2025
   - Noviembre 2025 es un mes futuro → Necesita análisis de octubre
   
2. **Primera Ejecución (2025-11):**
   - Solo 4 tickers descargados (rotación)
   - 0 trades generados (datos insuficientes)
   - **Solución:** Usar universo master (18 tickers)

3. **Tiempos de Ejecución:**
   - Descarga de datos: ~30 segundos
   - Generación de features: ~10 segundos
   - Entrenamiento ML: 5-10 minutos (26K registros)
   - Simulación completa: ~15 minutos total

---

## 🔧 Troubleshooting

### Si el pipeline falla:
1. Verificar que el entorno virtual esté activado:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. Verificar dependencias:
   ```powershell
   .\check_setup.ps1
   ```

3. Revisar logs de errores en la terminal

4. Re-ejecutar solo el paso fallido:
   ```powershell
   python scripts/<numero>_<nombre>.py --month 2025-10
   ```

---

## 📞 Soporte

Para más información, consultar:
- `SETUP.md` - Guía de configuración
- `requirements.txt` - Dependencias
- `policies/Policy_Base.json` - Configuración base
- Scripts individuales en `scripts/` (comentados)

---

**Estado actual:** ⏳ Pipeline en ejecución (entrenamiento de modelos)  
**Tiempo estimado restante:** ~10-15 minutos  
**Próxima actualización:** Al completar el entrenamiento
