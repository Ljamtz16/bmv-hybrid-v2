# USA Hybrid Clean V1 - Modo Intraday

Sistema de trading intradía con cierre obligatorio EOD (End of Day).

## 📋 Especificaciones

### Parámetros de Capital
- **Capital total máximo:** $1,000 USD
- **Capital por trade:** $250 USD
- **Máximo trades simultáneos:** 4
- **Máximo por ticker:** 1 operación

### Parámetros de Riesgo
- **Take Profit (TP):** 2.8%
- **Stop Loss (SL):** 0.5%
- **Cierre forzado EOD:** 15:55-16:00 NY
- **Cooldown:** 0 días (intradía)

### Filtros de Calidad
- **prob_win mínima:** 65%
- **P(TP≺SL) mínima:** 75%
- **ETTH máximo:** 0.25 días (~2 horas)
- **Spread máximo:** 5 basis points (0.05%)
- **ATR:** 0.6% - 2.0%

### Guardrails de Diversificación
- **Max sector share:** 60% del capital
- **Volumen mínimo:** P50 (mediana)
- **Ranking:** E[PnL] / ETTH

## 🗂️ Estructura de Archivos

```
usa_hybrid_clean_v1/
├── config/
│   └── intraday.yaml              # Configuración completa
├── data/
│   └── intraday/                  # Datos por fecha
│       └── YYYY-MM-DD/
│           ├── AMD.parquet
│           ├── NVDA.parquet
│           └── ...
├── features/
│   └── intraday/                  # Features por fecha
│       └── YYYY-MM-DD.parquet
├── reports/
│   └── intraday/                  # Resultados por fecha
│       └── YYYY-MM-DD/
│           ├── forecast_intraday.parquet
│           ├── trade_candidates_intraday.csv
│           ├── trade_plan_intraday.csv
│           ├── telegram_message.txt
│           ├── plan_stats.json
│           └── alerts.txt
├── models/
│   ├── clf_intraday.joblib        # Clasificador prob_win
│   ├── scaler_intraday.joblib     # Scaler de features
│   └── clf_intraday_metadata.yaml
└── scripts/
    ├── 00_download_intraday.py    # Descarga datos 15m/1h
    ├── 09_make_targets_intraday.py # Features + targets
    ├── 10_train_intraday.py       # Entrenar clasificador
    ├── 11_infer_and_gate_intraday.py # Inferencia
    ├── 35_eval_tp_sl_intraday.py # Evaluación TP/SL
    └── 40_make_trade_plan_intraday.py # Plan de trading
```

## 🚀 Uso Rápido

### 1. Ejecutar Pipeline Completo (una vez por día)

```powershell
# Ejecutar para hoy con tickers del master
.\run_intraday.ps1

# Ejecutar para fecha específica
.\run_intraday.ps1 -Date 2025-11-03

# Con tickers específicos
.\run_intraday.ps1 -Date 2025-11-03 -Tickers "AMD,NVDA,TSLA,AAPL,MSFT"

# Saltar descarga (si ya tienes los datos)
.\run_intraday.ps1 -SkipDownload -SkipFeatures
```

### 2. Configurar Evaluación Automática (cada 15 min)

```powershell
# Registrar tarea programada
.\setup_intraday_scheduler.ps1

# Ver qué haría sin ejecutar
.\setup_intraday_scheduler.ps1 -WhatIf

# Ejecutar manualmente el scheduler
.\schedule_intraday.ps1

# Forzar ejecución fuera de horario
.\schedule_intraday.ps1 -ForceRun
```

### 3. Evaluar Posiciones Manualmente

```powershell
# Evaluar posiciones actuales
python scripts\35_eval_tp_sl_intraday.py --date 2025-11-03

# Con notificaciones
python scripts\35_eval_tp_sl_intraday.py --date 2025-11-03 --notify
```

## 📚 Flujo de Trabajo Completo

### Fase 1: Preparación (Pre-mercado, antes de 9:30 AM NY)

```powershell
# 1. Descargar datos históricos para entrenamiento (una vez)
python scripts\00_download_intraday.py --start 2025-09-01 --end 2025-10-31 --tickers-file data\us\tickers_master.csv

# 2. Calcular features para entrenamiento
python scripts\09_make_targets_intraday.py --start 2025-09-01 --end 2025-10-31

# 3. Entrenar modelo
python scripts\10_train_intraday.py --start 2025-09-01 --end 2025-10-31

# 4. Ejecutar pipeline para hoy
.\run_intraday.ps1
```

### Fase 2: Operación (Durante mercado, 9:30 AM - 4:00 PM NY)

La tarea programada ejecutará automáticamente cada 15 minutos:

1. Verificar horario de mercado
2. Descargar precios actuales (15m)
3. Evaluar TP/SL para posiciones abiertas
4. Forzar cierre EOD si >= 15:55
5. Actualizar predictions_log_intraday.csv
6. Generar alertas

### Fase 3: Post-mercado (después de 4:00 PM NY)

```powershell
# Ver resumen del día
python scripts\31_aggregate_monthly_kpis.py --log data\trading\predictions_log_intraday.csv
```

## 📊 Salidas del Pipeline

### `forecast_intraday.parquet`
Señales filtradas con prob_win, features técnicos y liquidez.

### `trade_candidates_intraday.csv`
Top-15 candidatos rankeados por E[PnL]/ETTH.

### `trade_plan_intraday.csv`
Plan ejecutable (≤4 trades) con:
- ticker, sector
- entry_price, tp_price, sl_price
- qty, exposure
- prob_win, p_tp_before_sl, ETTH
- timestamp, status

### `telegram_message.txt`
Mensaje formateado para Telegram con resumen del plan.

### `plan_stats.json`
Métricas del plan:
```json
{
  "date": "2025-11-03",
  "n_signals_initial": 150,
  "n_signals_filtered": 25,
  "n_candidates": 15,
  "n_plan": 4,
  "total_exposure": 1000.0,
  "avg_prob_win": 0.72,
  "avg_etth": 0.18
}
```

### `alerts.txt`
Log de alertas durante la sesión:
```
14:45:23 - ✅ NVDA: TP_HIT @ $215.20 (PnL: +$6.08)
15:12:45 - ❌ AAPL: SL_HIT @ $269.96 (PnL: -$1.37)
15:55:00 - ⏹️ TSLA: EOD_CLOSE @ $465.00 (PnL: +$3.20)
```

## ⚙️ Configuración Avanzada

### Editar `config/intraday.yaml`

```yaml
capital:
  max_total: 1000
  per_trade_cash: 250
  max_open: 4

risk:
  tp_pct: 0.028    # Ajustar TP
  sl_pct: 0.005    # Ajustar SL

filters:
  prob_win_min: 0.65        # Más conservador: 0.70
  p_tp_before_sl_min: 0.75  # Más conservador: 0.80
  etth_max_days: 0.25       # Más rápido: 0.15 (1.5h)
```

### Personalizar Tickers

Editar `data/us/tickers_master.csv`:
```csv
ticker,sector,liquidity
AMD,Technology,high
NVDA,Technology,high
TSLA,Consumer,high
AAPL,Technology,high
MSFT,Technology,high
```

## 🔍 Monitoreo y Troubleshooting

### Ver estado de la tarea programada
```powershell
Get-ScheduledTask -TaskName "HybridClean_Intraday_Monitor_15m"
```

### Ver logs de ejecución
```powershell
# Alertas del día
Get-Content reports\intraday\2025-11-03\alerts.txt

# Ver plan generado
Import-Csv reports\intraday\2025-11-03\trade_plan_intraday.csv | Format-Table
```

### Desactivar temporalmente
```powershell
Disable-ScheduledTask -TaskName "HybridClean_Intraday_Monitor_15m"
```

### Reactivar
```powershell
Enable-ScheduledTask -TaskName "HybridClean_Intraday_Monitor_15m"
```

### Eliminar tarea
```powershell
Unregister-ScheduledTask -TaskName "HybridClean_Intraday_Monitor_15m" -Confirm:$false
```

## 🎯 Métricas Objetivo

| Métrica | Target | Actual |
|---------|--------|--------|
| Win Rate | ≥ 85% | TBD |
| PnL Diario | ≥ $20-25 | TBD |
| ETTH Promedio | ≤ 2 horas | TBD |
| Max Drawdown | ≤ 5% | TBD |
| Sharpe Ratio | ≥ 2.0 | TBD |

## 📈 Próximos Pasos

1. **Backtest 60-90 días** con datos históricos intraday
2. **Paper trading 10 días** para validar métricas
3. **Integrar TTH intraday** (scripts 38/39) para mejor ETTH
4. **Optimizar filtros** basado en resultados reales
5. **Automatizar Telegram** notificaciones en tiempo real
6. **Dashboard en tiempo real** (Streamlit/Dash)

## ⚠️ Advertencias

1. **Cierre EOD obligatorio:** Todas las posiciones se cierran a 15:55-16:00 NY
2. **Capital limitado:** Respeta el tope de $1,000 USD total
3. **Sin apalancamiento:** Operaciones con capital cash únicamente
4. **Horario de mercado:** Solo ejecuta 9:30-16:00 NY, lunes-viernes
5. **Datos en tiempo real:** Requiere conexión estable para yfinance
6. **Slippage:** No considerado en simulación, ajustar expectativas

---

**Última actualización:** 2025-11-03  
**Versión:** 1.0.0  
**Autor:** USA Hybrid Clean V1 Team

---

## 🧹 Limpieza del workspace antes de nuevas pruebas

1. Ensayo de limpieza (no borra nada):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean_workspace.ps1 -Mode Soft -DryRun -Yes
   ```

2. Limpieza real (mantiene datos crudos y configs):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean_workspace.ps1 -Mode Soft -Yes
   ```

3. Limpieza completa (incluye modelos entrenados):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean_workspace.ps1 -Mode Hard -Yes
   ```

4. Regenerar artefactos básicos:
   ```powershell
   python scripts\download_intraday_for_plan.py
   python scripts\monitor_intraday.py --once
   start intraday_dashboard.html
   ```

---

## 🎲 Reproducibilidad: gestión de seeds

Para experimentos reproducibles, todos los scripts usan una semilla global configurable:
- Prioridad: argumento `--seed` > variable de entorno `SEED` > valor por defecto (42).
- Ejemplo:
  ```powershell
  # Reproducible (semilla fija)
  python scripts\generate_synthetic_intraday.py --seed 123

  # Reproducible vía variable de entorno
  $env:SEED = 777
  python scripts\generate_synthetic_intraday.py

  # Estándar (usa 42 si no hay SEED ni --seed)
  python scripts\generate_synthetic_intraday.py
  ```

---
