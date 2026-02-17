# Guía de Prueba - Sistema Intraday

## ✅ Sistema Implementado y Funcionando

Acabas de probar exitosamente el pipeline intraday. Los componentes clave están operativos:
- ✅ Descarga datos 15m (26 barras/día = 6.5h trading)
- ✅ Calcula features técnicas (RSI, EMA, MACD, ATR, volumen, liquidez)
- ✅ Calcula targets TP/SL win/loss
- ✅ Scripts de patterns y TTH listos
- ✅ Notificador Telegram con dry-run

---

## 📋 Opciones de Prueba

### **Opción 1: Test Rápido (Validación)**
```powershell
# Test automático con pocos tickers
.\test_intraday_quick.ps1 -TestDate 2025-10-31 -TestTickers "AMD,NVDA,TSLA"

# Output esperado:
# - Descarga: ✅ 3/3 tickers (5 días lookback)
# - Features: ✅ 78 barras procesadas
# - Targets: ✅ Win/loss calculados
# - Telegram: ✅ Dry-run OK
```

**Duración:** ~2-3 minutos

---

### **Opción 2: Pipeline Completo (Sin Modelo)**
```powershell
# Ejecutar todo el pipeline pero sin inferencia (falta entrenar modelo)
.\run_intraday.ps1 -Date 2025-10-31 -Tickers "AMD,NVDA,TSLA,AAPL,MSFT"

# Pasos que ejecuta:
# 1. Download 15m → 5 tickers × 5 días
# 2. Features   → RSI, EMA, MACD, ATR, spreads
# 3. Inference  → SKIP (no hay modelo entrenado)
# 4. Patterns   → SKIP (necesita forecast)
# 5. TTH        → SKIP (necesita modelo TTH)
# 6. Plan       → SKIP (necesita forecast)
# 7. Telegram   → SKIP
```

**Duración:** ~5 minutos

---

### **Opción 3: Entrenar Modelos (Producción)**

#### **3.1) Descargar Históricos (60-90 días)**
```powershell
# Descargar 60 días de datos 15m
python scripts\00_download_intraday.py `
    --start 2025-09-01 `
    --end 2025-10-31 `
    --interval 15m `
    --tickers-file data\us\tickers_master.csv

# Tiempo: ~30-60 minutos (depende de #tickers)
# Espacio: ~500MB-1GB por mes
```

#### **3.2) Calcular Features Históricas**
```powershell
python scripts\09_make_targets_intraday.py `
    --start 2025-09-01 `
    --end 2025-10-31 `
    --interval 15m

# Output: features/intraday/*.parquet
# Tiempo: ~10-20 minutos
```

#### **3.3) Entrenar Clasificador**
```powershell
python scripts\10_train_intraday.py `
    --start 2025-09-01 `
    --end 2025-10-31 `
    --rolling-days 60

# Output: models/clf_intraday.joblib
# Tiempo: ~15-30 minutos
# Validación: ROC-AUC, Precision, Recall
```

#### **3.4) Entrenar TTH**
```powershell
python scripts\38_train_tth_intraday.py `
    --start 2025-09-01 `
    --end 2025-10-31

# Output: models/tth_hazard_intraday.joblib
# Tiempo: ~20-40 minutos
```

#### **3.5) Crear Calibración TTH**
```powershell
# Crear archivo inicial
@"
{
    "scale_tp": 1.0,
    "scale_sl": 1.0
}
"@ | Out-File -FilePath data\trading\tth_calibration_intraday.json -Encoding UTF8
```

**Duración total:** ~2-3 horas (depende de datos)

---

### **Opción 4: Pipeline Completo (Con Modelos)**

Una vez entrenados los modelos:

```powershell
# Ejecutar pipeline completo para hoy
.\run_intraday.ps1 `
    -Date (Get-Date -Format "yyyy-MM-dd") `
    -Tickers "AMD,NVDA,TSLA,AAPL,MSFT" `
    -NotifyTelegram

# Pasos que ejecuta:
# 1. Download   → Datos frescos 15m
# 2. Features   → RSI, EMA, MACD, ATR (19+ features)
# 3. Inference  → Prob_win con RF/XGB ✅
# 4. Patterns   → Hammer, Doji, Engulfing, etc. ✅
# 5. TTH        → ETTH y P(TP≺SL) con Monte Carlo ✅
# 6. Plan       → Top-4 señales con filtros+guardrails ✅
# 7. Telegram   → Notificación con plan del día ✅
```

**Output esperado:**
- `reports/intraday/YYYY-MM-DD/forecast_intraday.parquet` (con prob_win, patterns, ETTH)
- `reports/intraday/YYYY-MM-DD/trade_plan_intraday.csv` (Top-4 ejecutables)
- `reports/intraday/YYYY-MM-DD/telegram_message.txt` (mensaje formateado)

**Duración:** ~3-5 minutos

---

## 🔍 Validar Outputs

### **Verificar Descarga**
```powershell
# Ver datos descargados
dir data\intraday\2025-10-31\*.parquet

# Inspeccionar contenido
python -c "import pandas as pd; df = pd.read_parquet('data/intraday/2025-10-31/AMD.parquet'); print(df.head()); print(f'\nTotal barras: {len(df)}')"
```

### **Verificar Features**
```powershell
python -c "import pandas as pd; df = pd.read_parquet('features/intraday/2025-10-31.parquet'); print(df.columns.tolist()); print(f'\nShape: {df.shape}'); print(df[['ticker', 'close', 'rsi_14', 'atr_pct', 'win']].head())"
```

### **Verificar Forecast (si hay modelo)**
```powershell
python -c "import pandas as pd; df = pd.read_parquet('reports/intraday/2025-10-31/forecast_intraday.parquet'); print(f'Tickers: {df.ticker.nunique()}, Barras: {len(df)}'); print(df.nlargest(5, 'prob_win')[['ticker', 'timestamp', 'prob_win', 'etth_days', 'pattern_score']])"
```

### **Verificar Plan (si hay modelo)**
```powershell
python -c "import pandas as pd; plan = pd.read_csv('reports/intraday/2025-10-31/trade_plan_intraday.csv'); print(f'Señales: {len(plan)}'); print(plan[['ticker', 'entry_price', 'prob_win', 'expected_pnl', 'capital_allocated']])"
```

---

## 🤖 Configurar Telegram

```powershell
# Ejecutar configuración interactiva
.\setup_telegram.ps1

# Necesitas:
# 1. Token de @BotFather (formato: 123456789:ABCdefGHI...)
# 2. Chat ID de @userinfobot (formato: 987654321)

# Test dry-run
python scripts\33_notify_telegram_intraday.py --date 2025-10-31 --send-plan --dry-run

# Test real (envía mensaje)
python scripts\33_notify_telegram_intraday.py --date 2025-10-31 --send-plan
```

---

## ⏰ Automatizar con Task Scheduler

### **Registrar Tarea (15-min checks)**
```powershell
# Test WhatIf (no crea la tarea)
.\setup_intraday_scheduler.ps1 -WhatIf

# Registrar para real
.\setup_intraday_scheduler.ps1

# Verificar
Get-ScheduledTask -TaskName "HybridClean_Intraday_Monitor_15m"
```

**Configuración creada:**
- Trigger: Diario, repetir cada 15 minutos
- Horario: 08:00 - 18:00 (cubre 9:30-16:00 NY)
- Script: `schedule_intraday.ps1` (valida market hours automáticamente)

### **Ejecución Manual**
```powershell
# Simular lo que hace el scheduler
.\schedule_intraday.ps1 -Date 2025-10-31 -ForceRun

# Verifica:
# - Hora NY actual
# - Market hours (9:30-16:00)
# - Ejecuta 35_eval_tp_sl_intraday.py
# - Envía alertas si hay hits TP/SL
```

---

## 📊 Workflow Diario (Producción)

```
08:30 → Manual: Ejecutar run_intraday.ps1 para generar plan del día
         └─ Revisa top-4 señales en Telegram
         └─ Decide si ejecutar o ajustar

09:30 → Mercado abre
         └─ Task Scheduler ejecuta cada 15 min automáticamente

09:30-16:00 → Evaluación continua (cada 15 min)
               ├─ Descarga precios actuales
               ├─ Detecta TP/SL hits
               ├─ Genera alertas.txt
               └─ Envía notificaciones Telegram

15:55 → Cierre forzado EOD
         └─ Todas las posiciones OPEN → CLOSED

16:00 → Mercado cierra
         └─ Scheduler para hasta mañana

EOD → Revisar predictions_log_intraday.csv
       └─ Analizar win rate, PnL, ETTH accuracy
```

---

## 🐛 Troubleshooting

### **Sin Datos Descargados**
```powershell
# Problema: Fechas futuras o fines de semana
# Solución: Usar fechas de días de trading recientes

# Verificar último día disponible
python -c "import yfinance as yf; from datetime import datetime, timedelta; d = datetime.now() - timedelta(days=1); print(f'Try: {d.strftime(\"%Y-%m-%d\")}')"
```

### **Features con NaN**
```powershell
# RSI/EMA necesitan warmup (14-50 barras)
# lookback-days=5 da ~130 barras, suficiente para cálculo

# Si persiste, verificar:
python -c "import pandas as pd; df = pd.read_parquet('data/intraday/2025-10-31/AMD.parquet'); print(df.isnull().sum())"
```

### **Sin Señales Ejecutables**
```bash
# Filtros muy estrictos pueden rechazar todo:
# - prob_win >= 0.65
# - P(TP≺SL) >= 0.75
# - ETTH <= 0.25d
# - spread <= 5bps
# - ATR 0.6-2%

# Revisar forecast antes de filtros:
python -c "import pandas as pd; df = pd.read_parquet('reports/intraday/2025-10-31/forecast_intraday.parquet'); print(df[['prob_win', 'etth_days', 'spread_bps']].describe())"
```

### **Telegram No Envía**
```powershell
# 1. Verificar .env
Get-Content .env | Select-String "TELEGRAM"

# 2. Test manual
$env:TELEGRAM_TOKEN = "tu_token"
$env:TELEGRAM_CHAT_ID = "tu_chat_id"
python scripts\33_notify_telegram_intraday.py --date 2025-10-31 --send-plan

# 3. Throttling (solo envía cada 5 min del mismo tipo)
# Revisar: data/trading/telegram_state.json
```

---

## 📈 Siguiente: Backtesting y Paper Trading

```powershell
# 1. Backtest histórico (60 días)
# (próximo script: 41_backtest_intraday.py)

# 2. Paper trading (10 días)
# - Ejecutar pipeline real
# - NO ejecutar trades
# - Trackear win rate, PnL simulado

# 3. Ajustar parámetros:
# - Filtros (prob_win, P(TP≺SL), ETTH)
# - Calibración TTH (scale_tp, scale_sl)
# - Capital allocation (max_open, per_trade)

# 4. Go live cuando:
# - Win rate ≥85%
# - ETTH accuracy ≤±20%
# - Avg daily PnL ≥$20-25
```

---

## 🎯 Resumen de Tests Recomendados

| Test | Comando | Duración | Objetivo |
|------|---------|----------|----------|
| **Quick** | `.\test_intraday_quick.ps1` | 2-3 min | Validar componentes |
| **Features** | `python scripts\09_make_targets_intraday.py --date YYYY-MM-DD` | 1-2 min | Ver cálculo features |
| **Download** | `python scripts\00_download_intraday.py --date YYYY-MM-DD --tickers AMD,NVDA` | 1-2 min | Test descarga |
| **Full (sin modelo)** | `.\run_intraday.ps1 -Date YYYY-MM-DD` | 5 min | Pipeline completo |
| **Telegram** | `python scripts\33_notify_telegram_intraday.py --send-plan --dry-run` | 10 seg | Test notificaciones |

---

**¡Sistema listo para operar! 🚀**

Próximos pasos sugeridos:
1. ✅ Entrenar modelos con 60 días de datos
2. ✅ Configurar Telegram
3. ✅ Ejecutar pipeline completo con modelos
4. ✅ Backtest 60 días
5. ✅ Paper trading 10 días
6. 🎯 Go live con capital real
