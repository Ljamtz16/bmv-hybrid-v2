# RESUMEN COMPLETO DEL SISTEMA DE TRADING HÍBRIDO ML - USA MARKET

## 📊 ARQUITECTURA DEL SISTEMA

### 1. FUENTE DE DATOS
**Proveedor:** Alpaca Markets API
**Tipo:** Barras intraday de 15 minutos
**Cobertura:** 2022-01-01 hasta presente
**Tickers:** 18 acciones de alta liquidez (AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META, JPM, BAC, GS, MS, WFC, C, XLF, SPY, QQQ, DIA, IWM)
**Almacenamiento:** `data/us/intraday_15m/consolidated_15m.parquet`
**Actualización:** Manual via `download_alpaca_data.py`

---

## 🤖 MODELO PREDICTIVO

### Arquitectura
**Algoritmo:** XGBoost (Gradient Boosting)
**Estrategia:** Un modelo independiente por ticker (18 modelos)
**Target:** `prob_win` - Probabilidad de que el trade sea ganador
**Features:** 
- Indicadores técnicos: RSI, MACD, Bollinger Bands, ATR
- Patrones de precio: ETTH (Expected Time To Hit)
- Volumen y volatilidad
- Features de momentum y tendencia

### Entrenamiento
**Script:** `train_prob_win_model.py`
**Datos:** Trades históricos reales del backtest
**Carpeta:** `evidence/retrained_prob_win_robust/`
**Validación:** Walk-forward con división temporal

### Predicción
**Script:** `forecast_prob_win.py`
**Output:** `evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv`
**Métricas actuales:**
- Total predicciones: 5,097
- Prob_win promedio: 52.24%
- Señales BUY: 2,790 (54.7%)
- Señales SELL: 2,307 (45.3%)

---

## 📋 GENERACIÓN DE PLANES

### Script Principal
`generate_weekly_plans.py`

### Tipos de Planes

#### STANDARD
- **Objetivo:** Diversificación con prob_win ≥ 50%
- **Posiciones:** 3-5 por plan
- **Capital:** $2,000
- **Exposición máxima:** $600 por posición
- **Criterios:** Balance entre rentabilidad y riesgo

#### PROBWIN_55
- **Objetivo:** Máxima probabilidad de éxito
- **Posiciones:** 0-2 por plan (filtro estricto)
- **Capital:** $2,000
- **Exposición máxima:** $1,000 por posición
- **Criterios:** Solo trades con prob_win ≥ 55%

### Gestión de Riesgo
- **TP (Take Profit):** +1.6% del entry
- **SL (Stop Loss):** -1.0% del entry
- **Ratio Riesgo/Beneficio:** 1:1.6
- **ETTH (Expected Time To Hit):** Filtro de rapidez de ejecución

### Output
- `evidence/weekly_plans/plan_standard_YYYY-MM-DD.csv`
- `evidence/weekly_plans/plan_probwin55_YYYY-MM-DD.csv`

---

## 📈 DASHBOARD EN TIEMPO REAL

### Tecnología
**Framework:** Flask (Python)
**Puerto:** 7777
**Acceso Local:** http://localhost:7777
**Acceso LAN:** http://192.168.1.69:7777
**Script:** `dashboard_unified.py`

### Funcionalidades

#### Pestaña 1: Trade Monitor
- Posiciones activas en tiempo real
- Precios actualizados via yfinance (1 minuto)
- P&L dinámico calculado en vivo
- Estado del mercado NYSE (horario real con calendario)
- Indicadores: Entry, Current Price, TP, SL, % Change

#### Pestaña 2: Comparación de Planes
- Vista lado a lado: STANDARD vs PROBWIN_55
- Resumen ejecutivo: Posiciones, exposición, prob_win promedio
- Desglose de cada posición con TP/SL calculados
- Badges de confianza por color (verde ≥55%, amarillo 50-55%, rojo <50%)

#### Pestaña 3: Historial
- Todos los trades cerrados
- Filtros por ticker, lado (BUY/SELL), razón de cierre
- Métricas: Win rate, P&L total, promedio win/loss
- Gráficos de distribución

### Integración en Tiempo Real
- **pandas_market_calendars:** Horario exacto NYSE (9:30-16:00 ET)
- **pytz:** Timezone US/Eastern para precisión
- **yfinance:** Precios en tiempo real (actualización cada 30s)

---

## 🎯 EJECUCIÓN Y SEGUIMIENTO

### Archivos de Estado

#### Posiciones Activas
`val/trade_plan_EXECUTE.csv` - Plan cargado para ejecución

#### Historial de Trades
`val/trade_history_closed.csv` - Registro de todos los trades cerrados

### Flujo de Ejecución
1. Generar planes: `python generate_weekly_plans.py`
2. Cargar plan al dashboard (manualmente o via script)
3. Monitorear desde dashboard en tiempo real
4. Cerrar trades:
   - Automático: TP/SL alcanzado
   - Manual: Script de cierre personalizado

---

## 📊 RESULTADOS Y MÉTRICAS ACTUALES

### Performance Histórica (9 trades)
```
Win Rate:        66.7% (6 wins, 3 losses)
P&L Total:       $39.29
Win Promedio:    $9.28 (+1.53% avg)
Loss Promedio:   -$5.47 (-1.00% avg)
```

### Desglose por Exit Reason
```
TP (Take Profit):     5 trades (55.6%)
SL (Stop Loss):       3 trades (33.3%)
MANUAL_PROFIT:        1 trade (11.1%)
```

### Últimos 5 Trades
```
1. JPM BUY:  +$4.82 (+1.60%) - TP - 29/01/2026
2. MS BUY:   -$3.63 (-1.00%) - SL - 29/01/2026
3. GS BUY:   +$14.86 (+1.60%) - TP - 30/01/2026
4. GS BUY:   +$14.85 (+1.60%) - TP - 30/01/2026
5. MS BUY:   +$5.28 (+1.46%) - MANUAL - 01/02/2026
```

### Plan Activo (STANDARD - 29/01/2026)
```
Posiciones:          2 (JPM BUY, IWM SELL)
Exposición total:    $565.89
Prob_win promedio:   46.26%
Capital asignado:    $2,000
```

---

## 🏆 LOGROS ALCANZADOS

### ✅ Infraestructura de Datos
- Pipeline completo de descarga desde Alpaca
- Base de datos consolidada con 5,097 predicciones
- Cobertura histórica desde 2022

### ✅ Modelo Predictivo
- Sistema de ML funcional con prob_win como métrica clave
- Modelos independientes por ticker (18 modelos)
- Calibración en trades reales del backtest

### ✅ Generación de Planes
- 2 estrategias complementarias (STANDARD y PROBWIN_55)
- Gestión de riesgo automática (TP/SL calculados)
- Diversificación y filtros de calidad

### ✅ Dashboard en Tiempo Real
- Interfaz web moderna y responsive
- Precios actualizados en vivo con yfinance
- Horario de mercado preciso (NYSE calendar)
- 3 pestañas funcionales (Monitor, Comparación, Historial)
- Acceso local y desde red LAN

### ✅ Sistema de Ejecución
- Registro completo de trades cerrados
- Scripts para cierre manual y automático
- Métricas de performance en tiempo real

---

## 🔧 COMPONENTES PRINCIPALES

### Scripts de Datos
- `download_alpaca_data.py` - Descarga datos de Alpaca
- `consolidate_data.py` - Consolida múltiples archivos

### Scripts de Modelado
- `train_prob_win_model.py` - Entrena modelos por ticker
- `forecast_prob_win.py` - Genera predicciones

### Scripts de Trading
- `generate_weekly_plans.py` - Genera planes STANDARD y PROBWIN_55
- `dashboard_unified.py` - Dashboard web en tiempo real
- `close_trade.py` - Cierre manual de posiciones

### Utilidades
- `system_summary.py` - Resumen del sistema
- `show_signals_summary.py` - Análisis de señales
- `analyze_trades_output.py` - Análisis de resultados

---

## 📁 ESTRUCTURA DE CARPETAS

```
usa_hybrid_clean_v1/
├── data/us/intraday_15m/        # Datos de Alpaca
├── evidence/
│   ├── retrained_prob_win_robust/  # Modelos entrenados
│   ├── forecast_retrained_robust/  # Predicciones
│   └── weekly_plans/               # Planes generados
├── val/
│   ├── trade_plan_EXECUTE.csv      # Plan activo
│   └── trade_history_closed.csv    # Historial de trades
└── [scripts principales]
```

---

## 🚀 PRÓXIMOS PASOS SUGERIDOS

### Mejoras Técnicas
1. **Auto-ejecución:** Integración con broker API para trades automáticos
2. **Backtesting:** Validación histórica más extensa
3. **Feature engineering:** Incorporar más indicadores técnicos
4. **Ensemble models:** Combinar múltiples algoritmos

### Mejoras Operativas
1. **Alertas:** Notificaciones push cuando TP/SL alcanzados
2. **Análisis post-trade:** Dashboard de performance por ticker
3. **Optimización de parámetros:** Grid search para TP/SL óptimos
4. **Gestión de capital:** Position sizing dinámico

---

## 📞 ESTADO ACTUAL DEL SISTEMA

**Fecha:** 01/02/2026
**Estado:** Operativo y funcional
**Posiciones abiertas:** 2 (JPM, IWM)
**Dashboard:** Activo en http://192.168.1.69:7777
**Último trade:** MS +$5.28 cerrado manualmente (01/02/2026)
**Win rate acumulado:** 66.7%
**P&L acumulado:** +$39.29

---

*Sistema diseñado y desarrollado para trading algorítmico en mercado USA*
*Última actualización: 01/02/2026*
